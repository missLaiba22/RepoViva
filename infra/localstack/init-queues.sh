#!/bin/bash
# Run by LocalStack once it is ready (mounted into /etc/localstack/init/ready.d).
# Creates the queues with their DLQs, the event bus and its rules (decision 057).
# Safe to rerun.
set -euo pipefail

BUS=repoviva

create_queue_with_dlq() {
  local name="$1" dlq_url dlq_arn
  dlq_url=$(awslocal sqs create-queue --queue-name "${name}-dlq" --query QueueUrl --output text)
  dlq_arn=$(awslocal sqs get-queue-attributes --queue-url "${dlq_url}" \
    --attribute-names QueueArn --query Attributes.QueueArn --output text)
  awslocal sqs create-queue --queue-name "${name}" --attributes \
    "{\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${dlq_arn}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}" >/dev/null
  echo "created ${name} (+ ${name}-dlq)"
}

# Routes events of one type into a consumer's queue. InputPath delivers only
# the event's detail, which is our message envelope.
route_event() {
  local rule="$1" source="$2" detail_type="$3" queue="$4" queue_url queue_arn
  queue_url=$(awslocal sqs get-queue-url --queue-name "${queue}" --query QueueUrl --output text)
  queue_arn=$(awslocal sqs get-queue-attributes --queue-url "${queue_url}" \
    --attribute-names QueueArn --query Attributes.QueueArn --output text)
  awslocal events put-rule --name "${rule}" --event-bus-name "${BUS}" \
    --event-pattern "{\"source\":[\"${source}\"],\"detail-type\":[\"${detail_type}\"]}" >/dev/null
  awslocal events put-targets --rule "${rule}" --event-bus-name "${BUS}" \
    --targets "Id=${queue},Arn=${queue_arn},InputPath=\$.detail" >/dev/null
  echo "routed ${detail_type} -> ${queue}"
}

# Jobs
create_queue_with_dlq ingestion-jobs
create_queue_with_dlq report-jobs
create_queue_with_dlq planning-jobs

# Events
awslocal events describe-event-bus --name "${BUS}" >/dev/null 2>&1 \
  || awslocal events create-event-bus --name "${BUS}" >/dev/null
create_queue_with_dlq core-interview-events
create_queue_with_dlq evaluation-interview-events
route_event core-interview-ended repoviva.voice-service interview.ended core-interview-events
route_event evaluation-interview-ended repoviva.voice-service interview.ended evaluation-interview-events
