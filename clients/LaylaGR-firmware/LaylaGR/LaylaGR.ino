/*
 * LAYLA GR - ESP32 robot firmware v2
 * Hardware: ESP32 DevKit V1, L298N, HC-SR04 (front), PIR, 2x18650 motor pack, ESP on its own USB power.
 *
 * What changed from v1 (owner-flashed 2026-10-21):
 *   1. FORWARD now really drives the robot forwards (v1's FORWARD/REVERSE were swapped by the motor wiring).
 *      Left/right were already correct and are unchanged.
 *   2. The IR obstacle sensor and its gate are gone (the sensor is removed). GPIO23 is no longer used, so the
 *      3V3->GPIO23 jumper can be taken off.
 *   3. HC-SR04 on the front: publishes distance/state (cm) and refuses / stops FORWARD when something is
 *      closer than FRONT_STOP_CM. No sensor connected = no readings = never blocks.
 *   4. Publishes retained fw = "2" so the Layla server knows the directions are now correct at the source.
 *
 * Safety (unchanged idea): every command carries duration_ms (max 2000) and the motors stop when it runs out.
 * The Layla server sends short 600 ms bursts while a joystick is held, so a dropped link stops the robot.
 *
 * Serial @115200:  F 1000 | B 1000 | L 500 | R 500 | S | V 150 | D (distance) | STATUS
 * MQTT command:    tryvanta/robot/001/motor/set   {"action":"forward","speed":200,"duration_ms":600}
 *
 * OTA: after one USB flash the robot can be updated over Wi-Fi (arduino-cli upload with --protocol network).
 *
 * Wi-Fi and MQTT passwords live in secrets.h (same folder, never committed). See secrets.h.example.
 * Needs: ESP32 Arduino core 2.x (ledcSetup/ledcAttachPin API), library PubSubClient.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoOTA.h>
#include "secrets.h"

// ================= WIFI / MQTT =================
constexpr char WIFI_SSID[] = WIFI_SSID_VALUE;
constexpr char WIFI_PASS[] = WIFI_PASS_VALUE;

constexpr char MQTT_HOST[] = "layla.tryvanta.in";
constexpr uint16_t MQTT_PORT = 8883;
constexpr char MQTT_USER[] = "tvrobot";
constexpr char MQTT_PASS[] = MQTT_PASS_VALUE;
constexpr char MQTT_CLIENT_ID[] = "layla-robot-001";
constexpr char OTA_HOST[] = "layla-gr";        // Wi-Fi updates: no USB cable needed after the first flash
constexpr char OTA_PASS[] = OTA_PASS_VALUE;

constexpr char T_STATUS[]  = "tryvanta/robot/001/status";
constexpr char T_FW[]      = "tryvanta/robot/001/fw";
constexpr char T_IP[]      = "tryvanta/robot/001/ip";
constexpr char T_MOTORSET[] = "tryvanta/robot/001/motor/set";
constexpr char T_MOTORST[] = "tryvanta/robot/001/motor/state";
constexpr char T_OBST[]    = "tryvanta/robot/001/obstacle/state";
constexpr char T_DIST[]    = "tryvanta/robot/001/distance/state";
constexpr char T_PIR[]     = "tryvanta/robot/001/pir/state";

// ================= LET'S ENCRYPT ISRG ROOT X1 (valid to 2035) =================
const char ISRG_ROOT_X1[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4
WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu
ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY
MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc
h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+
0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U
A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW
T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH
B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC
B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv
KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn
OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn
jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw
qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI
rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV
HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq
hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL
ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ
3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK
NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5
ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur
TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC
jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc
oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq
4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA
mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d
emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=
-----END CERTIFICATE-----
)EOF";

// ================= PINS =================
constexpr uint8_t PIN_ENA = 25;
constexpr uint8_t PIN_IN1 = 26;
constexpr uint8_t PIN_IN2 = 27;
constexpr uint8_t PIN_IN3 = 14;
constexpr uint8_t PIN_IN4 = 12;   // strapping pin: fine while the L298N input does not pull it HIGH at boot
constexpr uint8_t PIN_ENB = 13;

constexpr uint8_t PIN_TRIG = 5;   // HC-SR04 TRIG
constexpr uint8_t PIN_ECHO = 19;  // HC-SR04 ECHO through a 1k/2k divider (5V -> 3.3V)
constexpr uint8_t PIN_PIR  = 32;

// ================= SETTINGS =================
constexpr uint32_t SERIAL_BAUD = 115200;
constexpr uint32_t PWM_FREQ = 1000;
constexpr uint8_t  PWM_BITS = 8;

constexpr uint32_t MAX_MOVE_MS = 2000;
constexpr uint32_t PIR_WARMUP_MS = 30000;
constexpr uint32_t SENSOR_LOG_MS = 1000;
constexpr uint8_t  DEFAULT_SPEED = 180;

constexpr uint32_t SONAR_EVERY_MS = 70;      // one ping every 70 ms (HC-SR04 needs >= 60 ms between pings)
constexpr uint32_t SONAR_TIMEOUT_US = 25000; // ~4.3 m round trip; longer = no echo
constexpr float    FRONT_STOP_CM = 20.0f;
constexpr uint8_t  BLOCK_CONFIRM = 2;        // consecutive close readings before we call it blocked
constexpr uint32_t DIST_PUB_MS = 1000;       // publish at least this often while readings exist

constexpr uint32_t MQTT_RETRY_MS = 5000;
constexpr uint32_t WIFI_RETRY_MS = 10000;

// ================= STATE =================
enum class Motion : uint8_t { STOPPED, FORWARD, REVERSE, LEFT, RIGHT };

Motion motion = Motion::STOPPED;
uint8_t motorSpeed = DEFAULT_SPEED;
uint32_t motionDeadline = 0;
uint32_t lastSensorLog = 0;

float distanceCm = -1.0f;         // -1 = no valid reading
uint32_t lastSonar = 0;
uint8_t closeCount = 0;
bool frontBlocked = false;
float lastPubDist = -100.0f;
uint32_t lastDistPub = 0;

bool pirMotionDetected = false;
String inputLine;

WiFiClientSecure net;
PubSubClient mqtt(net);
bool otaStarted = false;
uint32_t lastMqttTry = 0;
uint32_t lastWifiTry = 0;

Motion lastPubMotion = static_cast<Motion>(255);
uint8_t lastPubSpeed = 255;
int lastPubObst = -1;
int lastPubPir = -1;

// ================= HELPERS =================
const char* motionName(Motion m) {
  switch (m) {
    case Motion::FORWARD: return "FORWARD";
    case Motion::REVERSE: return "REVERSE";
    case Motion::LEFT:    return "LEFT";
    case Motion::RIGHT:   return "RIGHT";
    default:              return "STOPPED";
  }
}

bool timeReached(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}

String jsonStr(const String& s, const char* key) {
  String pat = String("\"") + key + "\"";
  int k = s.indexOf(pat);
  if (k < 0) return "";
  int c = s.indexOf(':', k + pat.length());
  if (c < 0) return "";
  int q1 = s.indexOf('"', c + 1);
  if (q1 < 0) return "";
  int q2 = s.indexOf('"', q1 + 1);
  if (q2 < 0) return "";
  return s.substring(q1 + 1, q2);
}

long jsonInt(const String& s, const char* key, long def) {
  String pat = String("\"") + key + "\"";
  int k = s.indexOf(pat);
  if (k < 0) return def;
  int c = s.indexOf(':', k + pat.length());
  if (c < 0) return def;
  int i = c + 1;
  while (i < (int)s.length() && (s[i] == ' ' || s[i] == '\t' || s[i] == '"')) i++;
  bool neg = false;
  if (i < (int)s.length() && s[i] == '-') { neg = true; i++; }
  long v = 0;
  bool any = false;
  while (i < (int)s.length() && isDigit(s[i])) { v = v * 10 + (s[i] - '0'); i++; any = true; }
  if (!any) return def;
  return neg ? -v : v;
}

// ================= MQTT PUBLISH =================
void publishMotorState() {
  if (!mqtt.connected()) return;
  char buf[80];
  snprintf(buf, sizeof(buf), "{\"action\":\"%s\",\"speed\":%u}", motionName(motion), motorSpeed);
  mqtt.publish(T_MOTORST, buf, true);
  lastPubMotion = motion;
  lastPubSpeed = motorSpeed;
}

void publishSensorStates(bool force) {
  if (!mqtt.connected()) return;
  int o = frontBlocked ? 1 : 0;
  int p = pirMotionDetected ? 1 : 0;
  if (force || o != lastPubObst) {
    mqtt.publish(T_OBST, o ? "blocked" : "clear", true);
    lastPubObst = o;
  }
  if (force || p != lastPubPir) {
    mqtt.publish(T_PIR, p ? "motion" : "quiet", true);
    lastPubPir = p;
  }
  uint32_t now = millis();
  if (distanceCm > 0 && (force || fabsf(distanceCm - lastPubDist) >= 2.0f || now - lastDistPub >= DIST_PUB_MS)) {
    char buf[16];
    snprintf(buf, sizeof(buf), "%.1f", distanceCm);
    mqtt.publish(T_DIST, buf, false);
    lastPubDist = distanceCm;
    lastDistPub = now;
  }
}

// ================= MOTORS =================
void stopMotors() {
  ledcWrite(0, 0);
  ledcWrite(1, 0);
  digitalWrite(PIN_IN1, LOW);
  digitalWrite(PIN_IN2, LOW);
  digitalWrite(PIN_IN3, LOW);
  digitalWrite(PIN_IN4, LOW);
  motion = Motion::STOPPED;
  motionDeadline = 0;
}

void applyMotion(Motion requested, uint32_t durationMs) {
  if (requested == Motion::STOPPED) {
    stopMotors();
    Serial.println("OK: motors stopped");
    publishMotorState();
    return;
  }
  if (durationMs == 0 || durationMs > MAX_MOVE_MS) {
    stopMotors();
    Serial.println("ERROR: duration must be 1-2000 ms");
    publishMotorState();
    return;
  }
  if (requested == Motion::FORWARD && frontBlocked) {
    stopMotors();
    Serial.println("BLOCKED: something close in front");
    publishMotorState();
    return;
  }

  // Re-issuing the SAME motion just extends the deadline: no stop/start stutter while a joystick is held.
  if (requested != motion) {
    stopMotors();
    switch (requested) {
      case Motion::FORWARD:   // v1 REVERSE pattern: on this robot's wiring it is the physical forward
        digitalWrite(PIN_IN1, LOW);  digitalWrite(PIN_IN2, HIGH);
        digitalWrite(PIN_IN3, LOW);  digitalWrite(PIN_IN4, HIGH);
        break;
      case Motion::REVERSE:   // v1 FORWARD pattern = physical reverse
        digitalWrite(PIN_IN1, HIGH); digitalWrite(PIN_IN2, LOW);
        digitalWrite(PIN_IN3, HIGH); digitalWrite(PIN_IN4, LOW);
        break;
      case Motion::LEFT:      // unchanged from v1 (owner confirmed correct)
        digitalWrite(PIN_IN1, LOW);  digitalWrite(PIN_IN2, HIGH);
        digitalWrite(PIN_IN3, HIGH); digitalWrite(PIN_IN4, LOW);
        break;
      case Motion::RIGHT:     // unchanged from v1 (owner confirmed correct)
        digitalWrite(PIN_IN1, HIGH); digitalWrite(PIN_IN2, LOW);
        digitalWrite(PIN_IN3, LOW);  digitalWrite(PIN_IN4, HIGH);
        break;
      default:
        stopMotors();
        return;
    }
  }
  ledcWrite(0, motorSpeed);
  ledcWrite(1, motorSpeed);
  bool changed = requested != motion;
  motion = requested;
  motionDeadline = millis() + durationMs;
  if (changed) {
    Serial.printf("OK: %s for %lu ms, speed=%u\n", motionName(motion), (unsigned long)durationMs, motorSpeed);
  }
  // motor/state is published from loop() whenever motion or speed actually changes
}

// ================= SENSORS =================
float readSonarCm() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(3);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  unsigned long us = pulseIn(PIN_ECHO, HIGH, SONAR_TIMEOUT_US);
  if (us == 0) return -1.0f;          // no echo / no sensor
  float cm = us / 58.0f;
  return (cm >= 2.0f && cm <= 400.0f) ? cm : -1.0f;
}

void updateSensors(uint32_t now) {
  if (now - lastSonar >= SONAR_EVERY_MS) {
    lastSonar = now;
    float cm = readSonarCm();
    distanceCm = cm;
    if (cm > 0 && cm < FRONT_STOP_CM) {
      if (closeCount < 255) closeCount++;
    } else {
      closeCount = 0;
    }
    bool blocked = closeCount >= BLOCK_CONFIRM;
    if (blocked != frontBlocked) {
      frontBlocked = blocked;
      Serial.printf("FRONT: %s (%.1f cm)\n", frontBlocked ? "BLOCKED" : "CLEAR", distanceCm);
    }
  }
  pirMotionDetected = (digitalRead(PIN_PIR) == HIGH);
  if (motion == Motion::FORWARD && frontBlocked) {
    stopMotors();
    Serial.println("SAFETY STOP: obstacle in front");
    publishMotorState();
  }
}

void printStatus(uint32_t now) {
  Serial.printf("STATUS fw=2 motion=%s speed=%u dist=%.1fcm front=%s PIR=%s wifi=%s mqtt=%s",
                motionName(motion), motorSpeed, distanceCm, frontBlocked ? "BLOCKED" : "CLEAR",
                pirMotionDetected ? "MOTION" : "QUIET", WiFi.status() == WL_CONNECTED ? "up" : "down",
                mqtt.connected() ? "up" : "down");
  if (now < PIR_WARMUP_MS) Serial.printf(" PIR_WARMUP=%lu_ms", (unsigned long)(PIR_WARMUP_MS - now));
  Serial.println();
}

// ================= MQTT IN =================
Motion actionToMotion(const String& a) {
  String u = a;
  u.trim();
  u.toUpperCase();
  if (u == "FORWARD") return Motion::FORWARD;
  if (u == "BACKWARD" || u == "REVERSE") return Motion::REVERSE;
  if (u == "LEFT") return Motion::LEFT;
  if (u == "RIGHT") return Motion::RIGHT;
  return Motion::STOPPED;
}

void mqttCallback(char* topic, byte* payload, unsigned int len) {
  if (String(topic) != T_MOTORSET) return;
  String msg;
  msg.reserve(len + 1);
  for (unsigned int i = 0; i < len; i++) msg += (char)payload[i];

  String act = jsonStr(msg, "action");
  long spd = jsonInt(msg, "speed", -1);
  long dur = jsonInt(msg, "duration_ms", 600);

  if (act.equalsIgnoreCase("STOP")) {      // stop is always accepted, whatever else the message says
    stopMotors();
    publishMotorState();
    return;
  }
  if (spd < 0 || spd > 255) {
    stopMotors();
    Serial.println("MQTT ERROR: speed must be 0..255");
    publishMotorState();
    return;
  }
  Motion m = actionToMotion(act);
  if (m == Motion::STOPPED) {
    stopMotors();
    Serial.println("MQTT ERROR: invalid action");
    publishMotorState();
    return;
  }
  if (dur < 1 || dur > (long)MAX_MOVE_MS) {
    stopMotors();
    Serial.println("MQTT ERROR: duration must be 1..2000 ms");
    publishMotorState();
    return;
  }
  motorSpeed = (uint8_t)spd;
  applyMotion(m, (uint32_t)dur);
}

void mqttReconnect(uint32_t now) {
  if (mqtt.connected() || WiFi.status() != WL_CONNECTED) return;
  if (lastMqttTry != 0 && now - lastMqttTry < MQTT_RETRY_MS) return;
  lastMqttTry = now;
  if (mqtt.connect(MQTT_CLIENT_ID, MQTT_USER, MQTT_PASS, T_STATUS, 1, true, "offline")) {
    Serial.println("MQTT connected");
    mqtt.publish(T_STATUS, "online", true);
    mqtt.publish(T_FW, "2", true);
    mqtt.publish(T_IP, WiFi.localIP().toString().c_str(), true);
    publishMotorState();
    publishSensorStates(true);
    mqtt.subscribe(T_MOTORSET, 1);
  } else {
    Serial.printf("MQTT connect failed, rc=%d\n", mqtt.state());
  }
}

void startOta() {
  if (otaStarted || WiFi.status() != WL_CONNECTED) return;
  ArduinoOTA.setHostname(OTA_HOST);
  ArduinoOTA.setPassword(OTA_PASS);
  ArduinoOTA.onStart([]() {
    stopMotors();                       // never flash a moving robot
    Serial.println("OTA: update starting, motors stopped");
  });
  ArduinoOTA.onEnd([]() { Serial.println("OTA: done, rebooting"); });
  ArduinoOTA.onError([](ota_error_t e) { Serial.printf("OTA error %u\n", (unsigned)e); });
  ArduinoOTA.begin();
  otaStarted = true;
  Serial.printf("OTA ready: %s.local / %s\n", OTA_HOST, WiFi.localIP().toString().c_str());
}

void ensureWifi(uint32_t now) {
  if (WiFi.status() == WL_CONNECTED) return;
  if (motion != Motion::STOPPED) {      // lost the network while moving: stop now, don't wait for the deadline
    stopMotors();
    Serial.println("WiFi lost: motors stopped");
  }
  if (lastWifiTry != 0 && now - lastWifiTry < WIFI_RETRY_MS) return;
  lastWifiTry = now;
  Serial.println("WiFi: connecting...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
}

// ================= SERIAL =================
void handleCommand(String line) {
  line.trim();
  line.toUpperCase();
  if (line.length() == 0) return;
  const int sep = line.indexOf(' ');
  String command = sep < 0 ? line : line.substring(0, sep);
  String argument = sep < 0 ? "" : line.substring(sep + 1);
  argument.trim();

  if (command == "S" || command == "STOP") { stopMotors(); publishMotorState(); Serial.println("OK: STOP"); return; }
  if (command == "STATUS") { printStatus(millis()); return; }
  if (command == "D") { Serial.printf("distance=%.1f cm front=%s\n", distanceCm, frontBlocked ? "BLOCKED" : "CLEAR"); return; }
  if (command == "V") {
    long value = argument.toInt();
    if (argument.length() == 0 || value < 0 || value > 255) { Serial.println("ERROR: use V 0..255"); return; }
    motorSpeed = (uint8_t)value;
    if (motion != Motion::STOPPED) { ledcWrite(0, motorSpeed); ledcWrite(1, motorSpeed); }
    publishMotorState();
    Serial.printf("OK: speed=%u\n", motorSpeed);
    return;
  }
  Motion requested;
  if (command == "F") requested = Motion::FORWARD;
  else if (command == "B") requested = Motion::REVERSE;
  else if (command == "L") requested = Motion::LEFT;
  else if (command == "R") requested = Motion::RIGHT;
  else { Serial.println("ERROR: use F/B/L/R <ms>, S, V <0-255>, D, STATUS"); return; }
  long duration = argument.toInt();
  if (duration < 1 || duration > (long)MAX_MOVE_MS) { Serial.println("ERROR: duration must be 1..2000 ms"); return; }
  applyMotion(requested, (uint32_t)duration);
}

// ================= SETUP / LOOP =================
void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(200);

  pinMode(PIN_IN1, OUTPUT);
  pinMode(PIN_IN2, OUTPUT);
  pinMode(PIN_IN3, OUTPUT);
  pinMode(PIN_IN4, OUTPUT);
  pinMode(PIN_TRIG, OUTPUT);
  digitalWrite(PIN_TRIG, LOW);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_PIR, INPUT);

  ledcSetup(0, PWM_FREQ, PWM_BITS);
  ledcAttachPin(PIN_ENA, 0);
  ledcSetup(1, PWM_FREQ, PWM_BITS);
  ledcAttachPin(PIN_ENB, 1);
  stopMotors();

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  net.setCACert(ISRG_ROOT_X1);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  mqtt.setKeepAlive(30);
  mqtt.setBufferSize(512);

  Serial.println();
  Serial.println("=== LAYLA GR BOOT (firmware v2) ===");
  Serial.println("Commands: F 500 | B 500 | L 300 | R 300 | S | V 180 | D | STATUS");
}

void loop() {
  const uint32_t now = millis();
  ensureWifi(now);
  mqttReconnect(now);
  mqtt.loop();
  startOta();
  if (otaStarted) ArduinoOTA.handle();

  updateSensors(now);
  publishSensorStates(false);
  if (motion != lastPubMotion || motorSpeed != lastPubSpeed) publishMotorState();

  if (motion != Motion::STOPPED && motionDeadline != 0 && timeReached(now, motionDeadline)) {
    stopMotors();
    publishMotorState();
    Serial.println("AUTO STOP: duration elapsed");
  }

  if (now - lastSensorLog >= SENSOR_LOG_MS) {
    lastSensorLog = now;
    if (now >= PIR_WARMUP_MS) {
      Serial.printf("SENSORS dist=%.1fcm front=%s PIR=%s\n", distanceCm, frontBlocked ? "BLOCKED" : "CLEAR",
                    pirMotionDetected ? "MOTION" : "QUIET");
    }
  }

  while (Serial.available() > 0) {
    const char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') { handleCommand(inputLine); inputLine = ""; }
    else if (inputLine.length() < 80) inputLine += c;
    else { inputLine = ""; stopMotors(); Serial.println("ERROR: command too long; motors stopped"); }
  }
  delay(2);
}
