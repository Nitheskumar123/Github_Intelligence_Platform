"""
GitHub Webhook handlers
Process incoming webhook events from GitHub
"""

import hmac
import hashlib
import json
import logging
from django.conf import settings
from django.utils import timezone
from .models import Repository, WebhookEvent, RepositoryWebhook
from .tasks import sync_repository_data

logger = logging.getLogger(__name__)


def verify_webhook_signature(payload_body, signature_header, secret):
    """
    Verify that the webhook payload was sent by GitHub
    """
    if not signature_header:
        return False
    
    # Get the signature from header
    sha_name, signature = signature_header.split('=')
    if sha_name != 'sha256':
        return False
    
    # Calculate expected signature
    mac = hmac.new(secret.encode(), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = mac.hexdigest()
    
    # Compare signatures
    return hmac.compare_digest(expected_signature, signature)


def process_webhook_event(event_type, delivery_id, payload, repository_full_name):
    """
    Process webhook event based on event type
    """
    try:
        # Find repository
        repository = Repository.objects.get(full_name=repository_full_name)
        
        # Create webhook event record
        webhook_event = WebhookEvent.objects.create(
            repository=repository,
            event_type=event_type,
            delivery_id=delivery_id,
            payload=payload,
            processed=False,
        )
        
        # Update webhook stats
        if hasattr(repository, 'webhook'):
            webhook = repository.webhook
            webhook.last_delivery_at = timezone.now()
            webhook.total_deliveries += 1
            webhook.save()
        
        # Process based on event type
        if event_type == 'push':
            handle_push_event(webhook_event)
        elif event_type == 'pull_request':
            handle_pull_request_event(webhook_event)
        elif event_type == 'issues':
            handle_issues_event(webhook_event)
        elif event_type == 'ping':
            handle_ping_event(webhook_event)
        else:
            logger.info(f"Unhandled event type: {event_type}")
        
        # Mark as processed
        webhook_event.processed = True
        webhook_event.processed_at = timezone.now()
        webhook_event.save()
        
        return True
        
    except Repository.DoesNotExist:
        logger.error(f"Repository not found: {repository_full_name}")
        return False
    except Exception as e:
        logger.error(f"Error processing webhook event: {e}")
        if 'webhook_event' in locals():
            webhook_event.error_message = str(e)
            webhook_event.save()
        return False


def handle_push_event(webhook_event):
    """
    Handle push event - new commits pushed
    """
    logger.info(f"Processing push event for {webhook_event.repository.full_name}")
    
    # Queue background task to sync commits
    from .tasks import sync_commits
    sync_commits.delay(webhook_event.repository.id)


def handle_pull_request_event(webhook_event):
    """
    Handle pull request event - PR opened, closed, merged, etc.
    """
    payload = webhook_event.payload
    action = payload.get('action')
    
    logger.info(f"Processing PR event ({action}) for {webhook_event.repository.full_name}")
    
    # Queue background task to sync pull requests
    from .tasks import sync_pull_requests
    sync_pull_requests.delay(webhook_event.repository.id)


def handle_issues_event(webhook_event):
    """
    Handle issues event - issue opened, closed, etc.
    """
    payload = webhook_event.payload
    action = payload.get('action')
    
    logger.info(f"Processing issue event ({action}) for {webhook_event.repository.full_name}")
    
    # Queue background task to sync issues
    from .tasks import sync_issues
    sync_issues.delay(webhook_event.repository.id)


def handle_ping_event(webhook_event):
    """
    Handle ping event - webhook setup confirmation
    """
    logger.info(f"Received ping event for {webhook_event.repository.full_name}")
    # Just log it, no action needed
# ... (keep all existing webhook handlers)

def handle_pull_request_event(webhook_event):
    """
    Handle pull request event - trigger analysis
    
    Args:
        webhook_event (WebhookEvent): Webhook event object
    """
    payload = webhook_event.payload
    action = payload.get('action')
    
    logger.info(f"Processing PR event ({action}) for {webhook_event.repository.full_name}")
    
    # Trigger analysis on opened or synchronize (updated)
    if action in ['opened', 'synchronize']:
        pr_data = payload.get('pull_request', {})
        pr_number = pr_data.get('number')
        
        if pr_number:
            # Find PR in database
            from .models import PullRequest
            from .tasks import analyze_pull_request
            
            try:
                pr = PullRequest.objects.get(
                    repository=webhook_event.repository,
                    number=pr_number
                )
                
                # Queue analysis task
                analyze_pull_request.delay(pr.id)
                logger.info(f"Queued analysis for PR #{pr_number}")
                
            except PullRequest.DoesNotExist:
                logger.warning(f"PR #{pr_number} not found in database, syncing first")
                # Sync PR then analyze
                from .tasks import sync_pull_requests
                sync_pull_requests.delay(webhook_event.repository.id)