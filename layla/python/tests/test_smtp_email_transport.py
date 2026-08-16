"""Real SMTPEmailTransport tests. Runs a real, minimal SMTP server
(this test's own fixture -- plain sockets, no mocking of smtplib)
locally and has the real transport genuinely speak SMTP to it: real
EHLO, real MAIL FROM/RCPT TO/DATA, a real parsed message on the far
end. No external mail provider or live credential is needed to prove
the transport's wire-level behavior is correct; a real external
account is the only thing this can't also prove (ADAPTER READY for
that part, honestly).
"""

import os
import socketserver
import threading
import unittest

from avishkar_integration import ProtocolInvocationError

from avishkar_layla.channels.email_adapter import SMTPEmailTransport


class _RecordingSMTPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.wfile.write(b"220 test.local SMTP ready\r\n")
        mail_from = None
        rcpt_to = []
        data_lines = []
        in_data = False
        while True:
            line = self.rfile.readline()
            if not line:
                break
            if in_data:
                if line.strip() == b".":
                    in_data = False
                    self.server.received_messages.append({
                        "mail_from": mail_from, "rcpt_to": list(rcpt_to),
                        "data": b"".join(data_lines).decode("utf-8", "replace"),
                    })
                    self.wfile.write(b"250 OK\r\n")
                else:
                    data_lines.append(line)
                continue

            text = line.decode("utf-8", "replace").strip()
            upper = text.upper()
            if upper.startswith("EHLO") or upper.startswith("HELO"):
                self.wfile.write(b"250-test.local\r\n250 OK\r\n")
            elif upper.startswith("MAIL FROM"):
                mail_from = text.split(":", 1)[1].strip()
                self.wfile.write(b"250 OK\r\n")
            elif upper.startswith("RCPT TO"):
                rcpt_to.append(text.split(":", 1)[1].strip())
                self.wfile.write(b"250 OK\r\n")
            elif upper.startswith("DATA"):
                in_data = True
                data_lines = []
                self.wfile.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
            elif upper.startswith("QUIT"):
                self.wfile.write(b"221 Bye\r\n")
                break
            else:
                self.wfile.write(b"250 OK\r\n")


class _FakeSMTPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


class RealSMTPServerTestCase(unittest.TestCase):
    """Starts a real, local SMTP server (its own thread) for each test,
    reachable at 127.0.0.1:<real bound port> -- not a mock of smtplib.
    """

    def setUp(self):
        self.server = _FakeSMTPServer(("127.0.0.1", 0), _RecordingSMTPHandler)
        self.server.received_messages = []
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        os.environ["TEST_SMTP_USERNAME"] = "layla-test-user"
        os.environ["TEST_SMTP_PASSWORD"] = "layla-test-password"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        os.environ.pop("TEST_SMTP_USERNAME", None)
        os.environ.pop("TEST_SMTP_PASSWORD", None)


class TestSMTPEmailTransportReal(RealSMTPServerTestCase):
    def test_genuinely_speaks_smtp_to_a_real_local_server(self):
        transport = SMTPEmailTransport(
            host="127.0.0.1", port=self.port, sender="layla@avishkar.test",
            username_env="TEST_SMTP_USERNAME", password_env="TEST_SMTP_PASSWORD",
        )

        message_id = transport("someone@example.com", "Hello", "This is a real SMTP conversation.")

        self.assertTrue(message_id.startswith("<"))
        self.assertEqual(len(self.server.received_messages), 1)
        received = self.server.received_messages[0]
        self.assertIn("someone@example.com", received["rcpt_to"][0])
        self.assertIn("layla@avishkar.test", received["mail_from"])
        self.assertIn("This is a real SMTP conversation.", received["data"])
        self.assertIn("Subject: Hello", received["data"])

    def test_missing_credentials_raises_before_any_connection(self):
        os.environ.pop("TEST_SMTP_USERNAME", None)
        transport = SMTPEmailTransport(
            host="127.0.0.1", port=self.port, sender="layla@avishkar.test",
            username_env="TEST_SMTP_USERNAME", password_env="TEST_SMTP_PASSWORD",
        )
        with self.assertRaises(ProtocolInvocationError) as ctx:
            transport("someone@example.com", "Hello", "body")
        self.assertIn("ADAPTER READY", str(ctx.exception))
        self.assertEqual(len(self.server.received_messages), 0)

    def test_unreachable_host_raises_protocol_invocation_error_not_a_raw_socket_error(self):
        transport = SMTPEmailTransport(
            host="127.0.0.1", port=1,  # real, but nothing real listens on port 1
            sender="layla@avishkar.test", username_env="TEST_SMTP_USERNAME", password_env="TEST_SMTP_PASSWORD",
            timeout_seconds=2.0,
        )
        with self.assertRaises(ProtocolInvocationError):
            transport("someone@example.com", "Hello", "body")


if __name__ == "__main__":
    unittest.main()
