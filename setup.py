#!/usr/bin/env python3
"""
Quick-start setup script for FaceID Portal.
Run this AFTER pip install -r requirements.txt
"""
import os
import sys
import subprocess

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'faceid.settings')

def run(cmd):
    print(f"\n▶ {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"  ⚠ Command exited with code {result.returncode}")
    return result.returncode == 0

print("=" * 55)
print("  FaceID Portal — Setup")
print("=" * 55)

# Migrate
run("python manage.py migrate")

# Create superuser
print("\n" + "─" * 55)
print("Create Admin (Superuser) Account")
print("─" * 55)
run("python manage.py createsuperuser --staff_id ADMIN-001")

# Collect static (optional for dev)
print("\n" + "─" * 55)
print("Collect static files")
run("python manage.py collectstatic --noinput")

print("\n" + "=" * 55)
print("  Setup complete!")
print("  Run: python manage.py runserver")
print("  Open: http://127.0.0.1:8000/")
print("=" * 55)
