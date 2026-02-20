#!/usr/bin/env python
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.tasks import sync_repository_data
from core.models import Repository
import time

print("\n" + "="*60)
print("TESTING FIXED CODE")
print("="*60 + "\n")

repo = Repository.objects.first()
print(f"Testing with: {repo.full_name}")

result = sync_repository_data.delay(repo.id)
print(f"Task ID: {result.id}")
print(f"Initial Status: {result.state}")

time.sleep(3)
print(f"Final Status: {result.state}")

print("\n✅ If no errors appeared above, the fix is working!\n")
print("="*60 + "\n")
