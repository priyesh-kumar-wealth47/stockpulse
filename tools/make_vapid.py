"""Run once on your laptop:  pip install cryptography   then   python tools/make_vapid.py
Prints the two VAPID keys used for push alerts."""
import base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
key = ec.generate_private_key(ec.SECP256R1())
private = b64(key.private_numbers().private_value.to_bytes(32, "big"))
public = b64(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
print("PUBLIC key  (goes in web/config.js as VAPID_PUBLIC_KEY):\n" + public)
print("\nPRIVATE key (goes in GitHub secret VAPID_PRIVATE_KEY, never in a file):\n" + private)
