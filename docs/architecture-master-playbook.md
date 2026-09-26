# Architecture Master Playbook

> **Purpose:** A single, living architecture document used to discover, analyze, decide, design, validate, operate, and evolve software systems.

---

# Architecture Thinking Model

The whole playbook always follows this chain:

```text
WHY
Business Problem
        ↓
WHAT
Requirements
        ↓
LIMITS
Constraints
        ↓
WHAT MATTERS
Architecture Drivers
        ↓
POSSIBILITIES
Architecture Options
        ↓
CONSEQUENCES
Trade-offs
        ↓
CHOICE
Architecture Decisions
        ↓
DESIGN
Target Architecture
        ↓
PROOF
Validation
        ↓
REALITY
Operations
        ↓
CHANGE
Evolution
```

Architecture must never start from technology.

The fundamental sequence is:

```text
Problem
→ Requirements
→ Constraints
→ Architecture Drivers
→ Options
→ Trade-offs
→ Decisions
→ Architecture
→ Technology
→ Validation
```

---

# 0. Project Intake & Architecture Overview

## Goal

Understand the project quickly before starting any deep analysis.

## Record

### Project Identification

- Project name
- Client / Business Unit
- Business owner
- Product owner
- Architecture owner
- Technical owner
- Delivery owner

### Project Type

```text
Greenfield
Brownfield
Modernization
Migration
Integration
Replatform
Refactor
Replacement
Expansion
```

### Project Classification

```text
Business Criticality
Low / Medium / High / Mission Critical

Technical Complexity
Low / Medium / High

Data Sensitivity
Public / Internal / Confidential / Restricted

Regulatory Impact
Low / Medium / High

Integration Complexity
Low / Medium / High

Availability Requirement
Standard / High / Mission Critical
```

### Executive Architecture Summary

Answer first:

- What is being built or changed?
- Why?
- For whom?
- What problem must be solved?
- What outcome is expected?
- Is there a current system?
- Are there relevant deadlines?
- Are there known constraints?
- What are the biggest known risks?

This section evolves as the project matures.

---

# 1. Business Context & Goals

## Main question

> **Why does this project exist?**

## Business Problem

Describe the current problem.

Avoid:

```text
We need to build a new application.
```

Prefer:

```text
The current process requires manual intervention,
takes about X hours
and has Y% rework.
```

## Business Context

Record:

- organization context;
- business process involved;
- current scenario;
- motivation for the initiative;
- existing problems;
- opportunities;
- current impacts.

## Business Goals

Define clear goals.

Examples:

```text
Reduce processing time
Increase automation
Reduce operational cost
Improve customer experience
Meet regulatory requirements
Enable business growth
```

## Expected Outcomes

Identify the expected outcomes.

## Success Criteria

Define how success will be measured.

## KPIs

When applicable:

```text
Processing time
Conversion rate
Operational cost
Failure rate
Automation rate
Customer satisfaction
Revenue
```

---

# 2. Scope, Stakeholders & System Context

## Main question

> **What is the boundary of the problem we are solving?**

## Scope

Record explicitly:

### In Scope

What is part of the initiative.

### Out of Scope

What is deliberately not part of it.

## Stakeholders

Identify:

```text
Business Sponsor
Product Owner
Business Analysts
Enterprise Architecture
Solution Architecture
Software Architecture
Development
Security
Infrastructure
Cloud
Network
Data
DevOps / Platform
Operations / SRE
Compliance
Vendors
External Organizations
```

For each stakeholder:

```text
Role
Interest
Responsibility
Decision Authority
Information Needed
```

## Actors

Identify users and consuming systems.

## System Context

Map:

```text
Users
System
External Systems
Upstream Systems
Downstream Systems
Third Parties
Data Sources
External Organizations
```

## Artifact

C4:

```text
System Context Diagram
```

---

# 3. Requirements

## Main question

> **What must the solution do and which properties must it have?**

Keep the requirement types strictly apart.

## 3.1 Business Requirements

Business needs.

```text
BR-001
```

## 3.2 Functional Requirements

System behaviors and capabilities.

```text
FR-001
FR-002
FR-003
```

Consider:

```text
Capabilities
Features
Use Cases
User Journeys
Business Processes
Workflows
Inputs
Outputs
Business Rules
Exception Flows
```

## 3.3 Non-Functional Requirements

Measurable requirements about the quality of the solution.

### Performance

```text
Latency
Response Time
Processing Time
Throughput
```

### Scalability

```text
Users
Concurrent Users
RPS
TPS
Growth
Peak Load
```

### Availability

```text
Availability target
Maintenance windows
Critical periods
```

### Reliability

```text
Failure tolerance
Error rate
Recovery behavior
```

### Resilience

```text
Failure scenarios
Retry
Timeout
Circuit Breaker
Bulkhead
Failover
```

### Disaster Recovery

```text
RPO
RTO
Backup
Restore
Failover
```

### Security

```text
Authentication
Authorization
Confidentiality
Integrity
Audit
Encryption
```

### Privacy

```text
PII
LGPD
Consent
Retention
Deletion
```

### Maintainability

### Testability

### Observability

### Auditability

### Interoperability

### Accessibility

### Portability

### Data Retention

### Compliance

### Cost

## Quantification Rule

Vague requirements must be turned into measurable criteria.

```text
Bad:
The system must be fast.

Good:
95% of requests must complete within 500 ms.
```

```text
Bad:
The application must be highly available.

Good:
The service must provide 99.95% monthly availability.
```

---

# 4. Current-State Assessment

This section is mandatory for brownfield and marked **N/A — Greenfield** when there really is no relevant current environment.

## Main question

> **Where are we today?**

## Application

Map:

```text
Applications
Services
Modules
Languages
Frameworks
Libraries
Dependencies
Architecture Style
Codebase
Technical Debt
```

## Infrastructure

```text
Cloud
On-premises
Compute
Network
Storage
DNS
Load Balancing
Regions
Availability Zones
Environments
```

## Data

```text
Databases
Schemas
Data Stores
Volume
Growth
Retention
Replication
Data Ownership
Data Quality
```

## Integration

```text
APIs
Messaging
Events
Files
Batch
Streaming
Third Parties
Legacy Protocols
```

## Security

```text
Identity
Authentication
Authorization
Network Boundaries
Secrets
Certificates
Encryption
Audit
Vulnerabilities
```

## DevOps

```text
Repositories
Branching
CI
CD
IaC
Artifacts
Environments
Deployment
Rollback
```

## Operations

```text
Monitoring
Logging
Tracing
Alerts
Incidents
Backup
DR
Support
```

## Assessment Result

Consolidate:

```text
Current State
Pain Points
Technical Debt
Risks
Limitations
Dependencies
Constraints
Opportunities
```

---

# 5. Constraints, Assumptions & Dependencies

## Main question

> **Which limits exist regardless of the desired architecture?**

## Constraints

Examples:

```text
Mandatory cloud provider
Mandatory technology
Legacy integration
Regulation
Budget ceiling
Deadline
Organizational policy
Existing contract
Approved products
Network restrictions
Data residency
```

## Assumptions

Everything taken as true without definitive confirmation.

Format:

```text
ID
Assumption
Reason
Impact if False
Validation Owner
Status
```

## Dependencies

Record dependencies:

```text
System
Team
Vendor
Infrastructure
API
Data
Approval
Contract
External Service
```

---

# 6. Architecture Drivers

## Main question

> **Which factors really determine the architecture?**

This is one of the central sections of the playbook.

Not every requirement is an Architecture Driver.

A requirement becomes a driver when it significantly changes:

```text
System Structure
Technology
Communication Model
Data Model
Deployment
Security
Scalability
Availability
Cost
Operational Complexity
```

## Driver Catalogue

For each driver:

```text
ID
Source Requirement
Description
Business Importance
Technical Impact
Priority
How it affects architecture
```

## Examples

```text
AD-001
99.99% availability
```

```text
AD-002
RTO < 15 minutes
```

```text
AD-003
100,000 concurrent users
```

```text
AD-004
p95 < 200 ms
```

```text
AD-005
10 TB/day ingestion
```

```text
AD-006
Mandatory LGPD compliance
```

---

# 7. Architecture Principles & Decision Criteria

## Main question

> **Which criteria will be used to evaluate solutions?**

Record the principles relevant to the project.

Examples:

```text
Security by Design
Least Privilege
Automation First
Infrastructure as Code
Observability by Design
Loose Coupling
High Cohesion
API First
Prefer Managed Services
Fail Gracefully
Design for Change
```

Do not turn principles into dogmas.

Each principle must exist to support goals or drivers.

## Decision Criteria

Possible criteria:

```text
Business Fit
Functional Fit
Performance
Availability
Scalability
Security
Complexity
Maintainability
Operability
Time-to-Market
Team Capability
Vendor Lock-in
Cost
Migration Effort
```

---

# 8. Architecture Analysis — Options & Trade-offs

## Main question

> **Which solutions are possible and what do we gain or lose with each one?**

Never record only the winning alternative.

For relevant decisions:

```text
Problem
Architecture Driver
Option A
Option B
Option C
Advantages
Disadvantages
Risks
Complexity
Cost
Operational Impact
Security Impact
Scalability Impact
Decision Criteria
Conclusion
```

## Analysis examples

```text
Modular Monolith vs Microservices
REST vs Messaging
Synchronous vs Asynchronous
SQL vs NoSQL
Container vs Serverless
Managed Service vs Self-managed
Active/Passive vs Active/Active
Single Region vs Multi-region
Build vs Buy
```

Architecture is essentially the conscious management of trade-offs.

---

# 9. Architecture Decisions

## Main question

> **What was decided, why, and what are the consequences?**

Decisions live in the document itself.

Standard format:

```text
ADR-001 — Decision Title

Status:
Proposed / Accepted / Superseded / Deprecated

Context
Problem
Architecture Drivers
Options Considered
Trade-offs
Decision
Rationale
Positive Consequences
Negative Consequences
Risks
Related Requirements
```

Do not keep ADRs disconnected from the rest of the architecture.

---

# 10. Target Architecture

## Main question

> **How will the solution work?**

This section represents the architecture that results from the previous decisions.

## 10.1 Domain & Functional View

Describe:

```text
Business Capabilities
Domains
Subdomains
Bounded Contexts
Responsibilities
Major Functional Areas
```

When DDD does not apply, use an equivalent functional decomposition.

## 10.2 System Context View

C4 Level 1.

Show:

```text
Users
System
External Systems
Interactions
System Boundary
```

## 10.3 Application / Container View

C4 Level 2.

Show:

```text
Applications
Services
APIs
Workers
Databases
Queues
External Dependencies
```

For each element:

```text
Responsibility
Technology
Owned Data
Interfaces
Dependencies
```

## 10.4 Component View

C4 Level 3 only when that level of detail adds value.

Show the relevant internal components.

## 10.5 Runtime View

Represent the critical flows.

Use:

```text
Sequence Diagrams
Dynamic Diagrams
Process Flows
```

Prioritize:

```text
Critical Business Flows
Failure Scenarios
Authentication Flow
Async Processing
Long-running Processes
```

## 10.6 Integration Architecture

For each integration:

```text
Source
Destination
Purpose
Protocol
Interface
Data
Frequency
Volume
Latency
Authentication
Authorization
Timeout
Retry
Idempotency
Error Handling
SLA
Ownership
```

Cover:

```text
REST
gRPC
Messaging
Events
Streaming
Files
Batch
Legacy
Third-party APIs
```

## 10.7 Data Architecture

Record:

```text
Data Domains
Entities
Ownership
Source of Truth
Read Patterns
Write Patterns
Volume
Growth
Consistency
Transactions
Retention
Archival
Deletion
Replication
Backup
Analytics
Reporting
Migration
```

Document decisions about:

```text
Relational
NoSQL
Cache
Object Storage
Search
Data Warehouse
Data Lake
```

## 10.8 Security Architecture

Document:

```text
Identity
Authentication
Authorization
RBAC / ABAC
Service Identity
Secrets
Certificates
Encryption at Rest
Encryption in Transit
Key Management
Network Segmentation
Trust Boundaries
Internet Exposure
Private Connectivity
API Security
Audit
Data Classification
Privacy
Compliance
Threat Model
```

## 10.9 Infrastructure Architecture

Show:

```text
Cloud / On-premises
Accounts / Subscriptions
Regions
Availability Zones
Network
Subnets
Routing
Firewalls
Load Balancing
DNS
Compute
Storage
Managed Services
```

## 10.10 Deployment Architecture

Show:

```text
Runtime Placement
Environments
Nodes
Containers
Functions
Clusters
Regions
Zones
Dependencies
Network Communication
```

---

# 11. Cross-Cutting Architecture

## Main question

> **Which concerns cut across the whole solution?**

This section avoids repeating concepts in each component.

## Reliability

```text
Timeout
Retry
Backoff
Circuit Breaker
Bulkhead
Failover
Graceful Degradation
Idempotency
```

## Scalability

```text
Horizontal Scaling
Vertical Scaling
Partitioning
Caching
Queueing
Load Distribution
```

## Performance

```text
Latency Budget
Caching
Concurrency
Connection Management
Batching
```

## Capacity

Record:

```text
Users
Concurrent Users
RPS
TPS
Peak TPS
Payload Size
Transactions/day
Storage
Growth
Bandwidth
Batch Size
Processing Time
```

## Observability

```text
Logs
Metrics
Traces
Dashboards
Alerts
Correlation IDs
Audit Logs
```

## Configuration

## Secrets Management

## Error Handling

## API Standards

## Data Governance

## Compliance

## Maintainability

## FinOps / Cost Architecture

Record:

```text
Major Cost Drivers
Expected Consumption
Cost Constraints
Scaling Impact
Licensing
Network Costs
Storage Growth
Optimization Opportunities
```

---

# 12. Delivery, Transition & Migration

## Main question

> **How will we move from the current state to the desired architecture?**

## Delivery Strategy

```text
Workstreams
Dependencies
Milestones
Architecture Enablers
Implementation Order
```

## Development

```text
Repository Strategy
Branching
Coding Standards
Code Review
Quality Gates
```

## CI/CD

```text
Build
Test
Security Scan
Artifact Management
Deployment
Rollback
```

## Infrastructure as Code

## Environment Strategy

```text
Development
Test
QA
Staging
Production
```

## Release Strategy

```text
Rolling
Blue/Green
Canary
Feature Flags
```

## Migration

When applicable:

```text
Current State
Transition Architecture
Target State
```

Record:

```text
Application Migration
Data Migration
Integration Migration
Cutover
Rollback
Coexistence
Decommissioning
```

---

# 13. Architecture Validation

## Main question

> **How will we prove that the architecture meets the requirements?**

Every important Architecture Driver must have some form of validation.

## Trace

```text
Requirement
↓
Architecture Driver
↓
Architecture Decision
↓
Architecture Component
↓
Validation
```

## Validation Methods

```text
Architecture Review
Proof of Concept
Prototype
Functional Test
Integration Test
Load Test
Performance Test
Stress Test
Resilience Test
Failover Test
Security Test
Penetration Test
Disaster Recovery Test
Backup Restore Test
```

## Example

```text
NFR-012

p95 < 300 ms

↓

AD-004

Latency is an architecture driver.

↓

ADR-007

Caching + horizontal scaling

↓

Performance Test

2,000 req/s

↓

PASS

p95 = 241 ms
```

---

# 14. Operational Architecture

## Main question

> **How will this solution survive in production?**

## Service Ownership

```text
Who owns the service?
Who operates it?
Who deploys it?
Who receives alerts?
Who handles incidents?
```

## Monitoring

## Logging

## Tracing

## Alerting

## SLI

## SLO

## SLA

## Incident Management

## On-call

## Runbooks

## Backup

## Restore

## Disaster Recovery

## Business Continuity

## Patch Management

## Certificate Rotation

## Secrets Rotation

## Capacity Monitoring

## Cost Monitoring

Mandatory question:

> **What happens at 03:00 when this system fails?**

---

# 15. Risks, Issues & Technical Debt

## Risk

An uncertain future event that may impact the project.

```text
Risk
Probability
Impact
Mitigation
Contingency
Owner
Status
```

## Issue

A problem that already exists.

## Technical Debt

Record:

```text
Debt
Reason
Impact
Risk
Remediation
Priority
```

---

# 16. Architecture Governance & Evolution

## Main question

> **How will the architecture stay healthy after the first delivery?**

Record:

```text
Architecture Reviews
Architecture Fitness
Technical Debt Reviews
Dependency Management
Capacity Reviews
Cost Reviews
Security Reviews
ADR Reviews
Technology Lifecycle
Deprecation
Modernization
Lessons Learned
```

## Architecture Roadmap

Organize as:

```text
Now
Next
Later
```

or:

```text
Current State
↓
Transition State 1
↓
Transition State 2
↓
Target State
```

---

# 17. Architecture Traceability

This section closes the loop.

Keep traceability:

```text
Business Goal
        ↓
Business Requirement
        ↓
Functional / Non-Functional Requirement
        ↓
Architecture Driver
        ↓
Architecture Analysis
        ↓
Architecture Decision
        ↓
Architecture Component
        ↓
Implementation
        ↓
Validation
        ↓
Operational Metric
```

An important architecture decision must be traceable to a real need.

---

# 18. Open Questions & Decisions Pending

Keep explicitly:

```text
ID
Question
Impact
Owner
Due Date
Status
```

Keep important doubts from staying hidden in meetings, chats or emails.

---

# 19. Glossary

Record specific terms:

```text
Business Terms
Domain Terms
Technical Terms
Acronyms
System Names
External Organizations
```

Use one canonical definition for each term.

---

# Architecture Quality Gates

The document follows the project's life cycle through the following gates.

## Gate 1 — Discovery Ready

- [ ] Business problem understood
- [ ] Business goals defined
- [ ] Stakeholders identified
- [ ] Scope established
- [ ] System context understood

## Gate 2 — Architecture Ready

- [ ] Functional requirements understood
- [ ] Critical NFRs quantified
- [ ] Constraints documented
- [ ] Current state assessed
- [ ] Dependencies identified
- [ ] Major risks identified
- [ ] Architecture drivers defined

## Gate 3 — Solution Ready

- [ ] Major options analyzed
- [ ] Trade-offs understood
- [ ] Architecture decisions recorded
- [ ] Target architecture documented
- [ ] Security addressed
- [ ] Data addressed
- [ ] Integrations addressed
- [ ] Deployment addressed

## Gate 4 — Build Ready

- [ ] Architecture understood by engineering
- [ ] Migration strategy defined
- [ ] Environments defined
- [ ] CI/CD defined
- [ ] Implementation dependencies known
- [ ] Validation strategy defined

## Gate 5 — Production Ready

- [ ] Critical NFRs validated
- [ ] Security validated
- [ ] Monitoring available
- [ ] Alerts configured
- [ ] Backup validated
- [ ] DR validated where required
- [ ] Runbooks available
- [ ] Ownership defined
- [ ] Rollback defined

## Gate 6 — Operationally Healthy

- [ ] SLOs monitored
- [ ] Capacity monitored
- [ ] Costs monitored
- [ ] Incidents reviewed
- [ ] Technical debt managed
- [ ] Architecture decisions revisited when necessary

---

# Rules of Use

## Rule 1

This is **a single living document**.

Do not create separate documents for:

```text
ADR
NFR
Security
Data
Integration
Risks
Assessment
```

These subjects remain sections of this playbook.

## Rule 2

All sections remain in the template.

When something does not apply:

```text
N/A — reason
```

Do not remove the section.

## Rule 3

The document grows progressively.

```text
Discovery
↓
Architecture
↓
Delivery
↓
Production
↓
Evolution
```

It does not need to be complete on day one.

## Rule 4

Do not choose technology before understanding the drivers.

```text
Business Problem
↓
Requirements
↓
Constraints
↓
Architecture Drivers
↓
Options
↓
Trade-offs
↓
Decisions
↓
Technology
```

## Rule 5

Every relevant architecture element must answer:

```text
Why does this exist?
```

## Rule 6

Every relevant decision must have:

```text
Reason
Trade-off
Consequence
```

## Rule 7

Every critical NFR must be:

```text
Measurable
Testable
Traceable
```

## Rule 8

Every critical Architecture Driver must end in validation.

```text
Driver
→ Decision
→ Architecture
→ Test
→ Evidence
```

---

# The Architect's Core Mental Model

When analyzing any problem, technology or solution, always answer:

```text
1. What problem are we solving?

2. Why does it matter?

3. What are the requirements?

4. What are the constraints?

5. What are the architecture drivers?

6. What options exist?

7. What are the trade-offs?

8. What decision are we making?

9. How does the architecture implement it?

10. How will we validate it?

11. How will we operate it?

12. How will it evolve?
```

This is the complete architecture cycle.
