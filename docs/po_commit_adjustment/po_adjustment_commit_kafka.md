# Account Head Commit Batch Processing - Implementation Documentation

## Purpose

This document defines a new batch-processing flow for account head commits.

Current situation:

- existing account head commit Kafka consumer accepts one row at a time
- existing API also accepts one commit at a time

New requirement:

- receive a list of account head commits in one request / one Kafka event
- process multiple rows in one batch
- keep this separate from the current single-row commit flow

This document is for design and implementation planning before code changes.

---

## Current System Status

## Existing single-row Kafka flow

Current incoming topic:

- `account-head-commit-events`

Defined in:

- [KafkaConfig.java](/Users/themysterious/Desktop/Computer/WorkingProjects/accounts_server_version/accounts/src/main/java/com/rnd/accounts/config/KafkaConfig.java:45)

Current consumer:

- [AccountHeadCommitConsumer.java](/Users/themysterious/Desktop/Computer/WorkingProjects/accounts_server_version/accounts/src/main/java/com/rnd/accounts/kafka/AccountHeadCommitConsumer.java:1)

Current behavior:

- parses one `KafkaEventEnvelope`
- maps one `AccountHeadCommitDto`
- validates one row
- processes one row
- publishes one response

So today the commit consumer is strictly single-record oriented.

---

## Existing single-row API flow

Current create API:

- `POST /api/account-head-commit/addAccountHeadCommit`

Current controller:

- [AccountHeadCommitController.java](/Users/themysterious/Desktop/Computer/WorkingProjects/accounts_server_version/accounts/src/main/java/com/rnd/accounts/controller/AccountHeadCommitController.java:1)

Current behavior:

- accepts one `AccountHeadCommitDto`
- saves one commit
- publishes one update event

So current REST flow is also single-record oriented.

---

## Requirement Clarification

The new batch flow should be:

- completely separate from the current single-row commit flow
- not a replacement of the current API/topic
- suitable for receiving multiple commit rows together from another application

This means:

- keep existing single-row topic
- keep existing single-row API
- add a new topic for commit list processing
- add a new API for commit list processing

---

## Recommendation

Do not modify the existing topic or the existing single-row endpoint contract.

Instead, add a parallel batch design:

## New Kafka topic

Recommended incoming topic:

- `account-head-commit-batch-events`

Recommended DLQ:

- `account-head-commit-batch-events-dlq`

Recommended update/outgoing response topic:

- reuse existing event response topic for batch processing result, or
- add a dedicated batch response topic if external system wants batch-specific consumption

Recommended first phase:

- keep using existing `event-responses` topic
- include only processing counts and row-level results in the response

---

## New API

Recommended REST endpoint:

- `POST /api/account-head-commit/batch`

This should accept a list of commits in one request.

Recommended request body:

```json
[ 
  {
    "transactionCommitNumber": 1,
    "projectNumber": "26RCHEMSP1122AKKU0002",
    "accountHeadId": 5,
    "transactionReceivedRefNumber": 8,
    "commitDate": "2026-05-22",
    "commitParticular": "HTR sensor for FID",
    "refDetails": null,
    "commitAmount": 49423.0,
    "status": "COMMITTED",
    "billAmount": null,
    "moduleId": "5",
    "frapAppId": "2026051526RCHEMSP1122AKKU0002-0673"
  },
  {
    "transactionCommitNumber": 2,
    "projectNumber": "26RCHEMSP1122AKKU0002",
    "accountHeadId": 6,
    "transactionReceivedRefNumber": 8,
    "commitDate": "2026-05-22",
    "commitParticular": "Second item",
    "refDetails": null,
    "commitAmount": 10000.0,
    "status": "COMMITTED",
    "billAmount": null,
    "moduleId": "5",
    "frapAppId": "2026051526RCHEMSP1122AKKU0002-0674"
  }
]
```

Reason for raw array recommendation:

- simplest payload
- matches your actual requirement
- no unnecessary wrapper field like `commits`

---

## New DTOs Required

Recommended DTOs:

## 1. Batch item result DTO

`AccountHeadCommitBatchItemResultDto`

Fields:

- `index`
- `transactionCommitNumber`
- `projectNumber`
- `accountHeadId`
- `status`
- `message`
- `savedCommitNumber`

## 2. Batch response DTO

`AccountHeadCommitBatchResponseDto`

Fields:

- `requestedCount`
- `successCount`
- `failureCount`
- `results`

---

## Kafka Event Shape

Recommended batch Kafka event:

```json
{
  "schemaVersion": "1.0",
  "eventType": "ACCOUNT_HEAD_COMMIT_BATCH",
  "timestamp": "2026-06-09T12:00:00",
  "data": [
    {
      "transactionCommitNumber": 1,
      "projectNumber": "26RCHEMSP1122AKKU0002",
      "accountHeadId": 5,
      "transactionReceivedRefNumber": 8,
      "commitDate": "2026-05-22",
      "commitParticular": "HTR sensor for FID",
      "refDetails": null,
      "commitAmount": 49423.0,
      "status": "COMMITTED",
      "billAmount": null,
      "moduleId": "5",
      "frapAppId": "2026051526RCHEMSP1122AKKU0002-0673"
    }
  ]
}
```

---

## Batch Consumer Design

Recommended new consumer:

- `AccountHeadCommitBatchConsumer`

Recommended topic:

- `KafkaConfig.ACCOUNT_HEAD_COMMIT_BATCH_INCOMING_TOPIC`

Recommended behavior:

1. parse one batch envelope
2. map `data` to `List<AccountHeadCommitDto>`
3. validate top-level batch
4. iterate through the list
5. process each row independently
6. collect per-row success/failure
7. publish one batch response event
8. acknowledge Kafka message once batch processing completes

---

## Processing Rule

Recommended processing mode:

- row-by-row processing inside one batch request
- one bad row should not fail the entire batch by default

Reason:

- better operational resilience
- easier for upstream system
- avoids replaying already successful rows

So recommended result type is:

- partial success allowed

Example response:

```json
{
  "requestedCount": 3,
  "successCount": 2,
  "failureCount": 1,
  "results": [
    {
      "index": 0,
      "transactionCommitNumber": 1,
      "projectNumber": "26RCHEMSP1122AKKU0002",
      "accountHeadId": 5,
      "status": "SUCCESS",
      "message": "Commit processed successfully",
      "savedCommitNumber": 501
    },
    {
      "index": 1,
      "transactionCommitNumber": 2,
      "projectNumber": "26RCHEMSP1122AKKU0002",
      "accountHeadId": 6,
      "status": "FAILED",
      "message": "Account Head not found",
      "savedCommitNumber": null
    }
  ]
}
```

---

## Idempotency Recommendation

For batch processing, idempotency should still be row-level.

Recommended row key:

- `transactionCommitNumber + projectNumber + accountHeadId`

This matches the current uniqueness probe style already used in single-row consumer logic.

Recommended behavior:

- if one row is already processed, mark that row as success with message:
  - `Already processed`
- continue processing remaining rows

Do not reject the full batch just because one row is duplicate.

---

## Service Layer Recommendation

Do not put batch orchestration inside the existing single-row service method directly.

Recommended design:

## Keep existing single-row service

- `processIncomingCommit(AccountHeadCommitDto dto)`

## Add new batch service method

- `processIncomingCommitBatch(List<AccountHeadCommitDto> commits)`

Recommended implementation:

- batch method loops over each commit DTO
- internally calls existing single-row method for each row

This avoids rewriting all commit business rules twice.

---

## Transaction Strategy

Recommended strategy:

- each row should be processed in its own transaction boundary

Reason:

- if row 5 fails, rows 1 to 4 should remain committed
- partial success is easier to support safely

Recommended implementation options:

1. batch service calls a transactional single-row processor per item
2. use `REQUIRES_NEW` for each row if needed

Best recommendation:

- keep outer batch orchestration non-transactional
- process each item using existing transactional single-row method

---

## REST API Behavior

Recommended endpoint:

- `POST /api/account-head-commit/batch`

Response should be:

- `200 OK` if batch request parsed and processed, even if some rows failed
- `400 Bad Request` only if batch request itself is malformed

Recommended response rules:

- if top-level array invalid -> reject whole request
- if specific row invalid -> capture that row failure only

---

## Kafka Response Behavior

Recommended event type:

- `ACCOUNT_HEAD_COMMIT_BATCH_RESPONSE`

Recommended response metadata:

- `requestedCount`
- `successCount`
- `failureCount`

Use existing response topic if possible:

- keeps operational model simpler

---

## Security

Recommended access for REST batch API:

- `ADMIN`
- `ACCOUNTS`
- `ACCOUNTS_ASSISTANT`

Same as the normal commit APIs.

---

## Validation Rules

Top-level batch validation:

- commit list must not be null
- commit list must not be empty

Per-row validation:

- `projectNumber` required
- `accountHeadId` required
- `commitAmount` required where business logic needs it
- `moduleId` validated if present
- existing single-row validations should continue applying

---

## API Plan

## New Kafka topics to add

- `ACCOUNT_HEAD_COMMIT_BATCH_INCOMING_TOPIC = "account-head-commit-batch-events"`
- `ACCOUNT_HEAD_COMMIT_BATCH_DLQ_TOPIC = "account-head-commit-batch-events-dlq"`

Optional:

- `ACCOUNT_HEAD_COMMIT_BATCH_UPDATE_OUTGOING_TOPIC`

Recommended first phase:

- do not add a separate update topic unless upstream explicitly needs it
- use existing event response topic for processing result

## New backend components

- `AccountHeadCommitBatchConsumer`
- `AccountHeadCommitBatchResponseDto`
- `AccountHeadCommitBatchItemResultDto`
- batch service method in commit service
- `POST /api/account-head-commit/batch`

---

## Recommended Implementation Order

1. add batch DTOs
2. add Kafka config constants and topic beans
3. add batch consumer
4. add batch service orchestration method
5. add batch REST API
6. add API summary doc entry

---

## Conclusion

The current account head commit flow is single-row only.

For your requirement, the correct design is:

- keep current single-row topic and API unchanged
- add a separate batch topic
- add a separate batch API
- process each commit row independently inside the batch
- return one batch response with row-level success/failure

This is the safest way to support multi-row commit processing without breaking the current account head commit integration.
