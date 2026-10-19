#!/bin/bash
# Real-AWS version of infra/localstack/init-queues.sh (decisions 057, 063).
# Run in AWS CloudShell, in the region the EC2 instance uses:
#   bash setup-messaging.sh
# Creates the queues with their DLQs, the event bus and its rules. Unlike
# LocalStack, AWS only lets a rule deliver into a queue whose policy allows
# it, so each event queue gets one. Safe to rerun.
set -euo pipefail

BUS=repoviva
REGION=$(aws configure get region || echo "${AWS_REGION}")
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

queue_arn() {
  echo "arn:aws:sqs:${REGION}:${ACCOUNT}:$1"
}

create_queue_with_dlq() {
  local name="$1" redrive
  aws sqs create-queue --queue-name "${name}-dlq" >/dev/null
  redrive=$(jq -nc --arg dlq "$(queue_arn "${name}-dlq")" \
    '{RedrivePolicy: ({deadLetterTargetArn: $dlq, maxReceiveCount: "3"} | tojson)}')
  aws sqs create-queue --queue-name "${name}" --attributes "${redrive}" >/dev/null
  echo "created ${name} (+ ${name}-dlq)"
}

# Routes events into a consumer's queue. detail_types is a JSON list body,
# e.g. '"a","b"'. InputPath delivers only the event's detail, which is our
# message envelope.
route_event() {
  local rule="$1" source="$2" detail_types="$3" queue="$4" queue_url rule_arn policy
  queue_url=$(aws sqs get-queue-url --queue-name "${queue}" --query QueueUrl --output text)
  rule_arn=$(aws events put-rule --name "${rule}" --event-bus-name "${BUS}" \
    --event-pattern "{\"source\":[\"${source}\"],\"detail-type\":[${detail_types}]}" \
    --query RuleArn --output text)
  policy=$(jq -nc --arg q "$(queue_arn "${queue}")" --arg r "${rule_arn}" '{Policy: ({
    Version: "2012-10-17",
    Statement: [{Effect: "Allow", Principal: {Service: "events.amazonaws.com"},
      Action: "sqs:SendMessage", Resource: $q,
      Condition: {ArnEquals: {"aws:SourceArn": $r}}}]
  } | tojson)}')
  aws sqs set-queue-attributes --queue-url "${queue_url}" --attributes "${policy}"
  aws events put-targets --rule "${rule}" --event-bus-name "${BUS}" \
    --targets "Id=${queue},Arn=$(queue_arn "${queue}"),InputPath=\$.detail" >/dev/null
  echo "routed ${detail_types} -> ${queue}"
}

# Jobs
create_queue_with_dlq ingestion-jobs
create_queue_with_dlq report-jobs
create_queue_with_dlq planning-jobs

# Events
aws events describe-event-bus --name "${BUS}" >/dev/null 2>&1 \
  || aws events create-event-bus --name "${BUS}" >/dev/null
create_queue_with_dlq core-interview-events
create_queue_with_dlq evaluation-interview-events
create_queue_with_dlq core-ingestion-events
route_event core-interview-ended repoviva.voice-service '"interview.ended"' core-interview-events
route_event evaluation-interview-ended repoviva.voice-service '"interview.ended"' evaluation-interview-events
route_event core-ingestion repoviva.repository-service   '"ingestion.started","ingestion.completed","ingestion.failed"' core-ingestion-events

echo
echo "Queue URLs for the .env.prod files:"
for q in ingestion-jobs report-jobs planning-jobs core-interview-events evaluation-interview-events core-ingestion-events; do
  echo "  ${q}: https://sqs.${REGION}.amazonaws.com/${ACCOUNT}/${q}"
done
