#!/bin/bash
# Run by LocalStack once it is ready (mounted into /etc/localstack/init/ready.d).
# Creates every queue with its DLQ (decision 057). Safe to rerun.
set -euo pipefail

create_queue_with_dlq() {
  local name="$1" dlq_url dlq_arn
  dlq_url=$(awslocal sqs create-queue --queue-name "${name}-dlq" --query QueueUrl --output text)
  dlq_arn=$(awslocal sqs get-queue-attributes --queue-url "${dlq_url}" \
    --attribute-names QueueArn --query Attributes.QueueArn --output text)
  awslocal sqs create-queue --queue-name "${name}" --attributes \
    "{\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${dlq_arn}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}" >/dev/null
  echo "created ${name} (+ ${name}-dlq)"
}

create_queue_with_dlq ingestion-jobs
