import hashlib

candidates = [
    "Admin123", "Admin@123", "Global@123", "Admin1234", "admin1234", 
    "Admin@1234", "Global123", "Global1234", "password", "123456",
    "Admin1234!", "Admin1234@", "manish@1234", "Manish@1234"
]

for c in candidates:
    h = hashlib.sha256(c.encode()).hexdigest()
    print(f"{c:15}: {h}")

# Target from brute_manish.py
target_manish = "ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f"
# Target from brute_hash.py
target_hash = "60fe74406e7f353ed979f350f2fbb6a2e8690a5fa7d1b0c32983d1d8b3f95f67"

print(f"\nTarget Manish:  {target_manish}")
print(f"Target General: {target_hash}")
