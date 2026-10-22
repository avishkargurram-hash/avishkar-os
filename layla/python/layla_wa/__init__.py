"""Autonomous WhatsApp replies on the owner's behalf.

Server half of the LaylaWaAgent Android app. The phone relays incoming
notifications here; this package decides whether and what to reply, and the
phone sends the reply through the notification's own RemoteInput action.
The model has no tools; every send is gated by the kill switch twice.
"""
