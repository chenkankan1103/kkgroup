#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-kkgroup}"
ZONE="${ZONE:-us-central1-a}"
INSTANCE="${INSTANCE:-instance-20250501-142333}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-github-actions-vm-repair@kkgroup.iam.gserviceaccount.com}"
MEMBER="serviceAccount:${SERVICE_ACCOUNT}"

echo "Granting IAP/SSH repair access to ${MEMBER} on ${PROJECT_ID}/${ZONE}/${INSTANCE}"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="$MEMBER" \
  --role="roles/iap.tunnelResourceAccessor"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="$MEMBER" \
  --role="roles/compute.osLogin"

# gcloud compute ssh updates SSH metadata when OS Login is not active for the VM.
# Keep this binding until OS Login is verified end to end.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="$MEMBER" \
  --role="roles/compute.instanceAdmin.v1"

gcloud compute ssh "$INSTANCE" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --tunnel-through-iap \
  --troubleshoot
