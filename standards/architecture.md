# Architecture Standards - {{PROJECT_NAME}}

> Architecture Pattern: {{ARCHITECTURE_TYPE}}
> Tech Stack: {{TECH_STACK}}

## Architecture Pattern

This project follows the **{{ARCHITECTURE_TYPE}}** pattern. All new code must conform to this architecture unless a deviation is explicitly approved and documented.

### Core Principles
- Separation of concerns: each layer and component has a single, well-defined responsibility.
- Depend on abstractions, not concretions.
- Business logic must remain independent of frameworks, databases, and external services.
- Changes to one layer should not ripple across unrelated layers.

## Layer Responsibilities

### Presentation / Interface Layer
- **Does**: handle user interaction, input validation at the UI level, display formatting, routing.
- **Does NOT**: contain business rules, directly access the database, or manage application state beyond view-specific concerns.

### Application / Service Layer
- **Does**: orchestrate use cases, coordinate between domain and infrastructure, enforce authorization, manage transactions.
- **Does NOT**: contain business rules (those belong in Domain) or directly serialize responses (that belongs in Presentation).

### Domain / Business Layer
- **Does**: encapsulate core business rules, domain models, value objects, domain events.
- **Does NOT**: depend on any external framework, database, or transport mechanism.

### Infrastructure / Data Layer
- **Does**: implement persistence, external API calls, messaging, file I/O, and other technical concerns.
- **Does NOT**: contain business logic. It implements interfaces defined by upper layers.

## Dependency Rules

- Dependencies point **inward**: Presentation -> Application -> Domain. Infrastructure implements Domain interfaces.
- **Never** import from Presentation in Domain or Infrastructure.
- **Never** import from Infrastructure in Domain.
- Application layer may depend on Domain and on Infrastructure abstractions (interfaces), but not on concrete implementations.
- Use dependency injection to provide concrete implementations at runtime.

### Import Matrix

| From \ To          | Presentation | Application | Domain | Infrastructure |
|--------------------|:---:|:---:|:---:|:---:|
| **Presentation**   | -   | yes | yes | no  |
| **Application**    | no  | -   | yes | interfaces only |
| **Domain**         | no  | no  | -   | no  |
| **Infrastructure** | no  | no  | yes (implements) | - |

## Component Boundaries

Split a component into smaller parts when:
- It handles more than one aggregate or domain concept.
- Its file count exceeds ~15 files or its mental model cannot be explained in 2 sentences.
- Two teams need to evolve parts of it independently.
- It has distinct scaling, deployment, or testing requirements.

Keep components merged when:
- Splitting would create excessive cross-component coupling.
- The concepts share the same lifecycle and change together.

## State Management

- Application state should have a **single source of truth**. Avoid duplicating state across layers.
- Transient UI state (form values, toggle states) lives in the Presentation layer.
- Persistent domain state lives in the Domain layer and is hydrated from Infrastructure.
- Prefer explicit state transitions over implicit mutations. Model state changes as events or commands where appropriate.
- Document the state flow for any non-trivial feature: where state originates, how it transforms, and where it is consumed.

## API Design

### Endpoint Patterns
- Use consistent, resource-oriented URL structures (e.g., `/api/v1/users/{id}/orders`).
- Use HTTP methods semantically: `GET` (read), `POST` (create), `PUT`/`PATCH` (update), `DELETE` (remove).
- Version APIs explicitly in the URL or header.

### Request / Response Conventions
- Request bodies use camelCase (JSON) or snake_case — pick one and enforce it project-wide.
- Responses include a consistent envelope: `{ "data": ..., "meta": ... }` or direct resource representation — choose one pattern.
- Error responses follow a standard shape: `{ "error": { "code": "...", "message": "..." } }`.
- Paginate list endpoints. Include `page`, `pageSize`, and `totalCount` in responses.

### Contract Rules
- All API changes must be backward compatible unless a new version is introduced.
- Document all endpoints. Use OpenAPI/Swagger or equivalent for {{TECH_STACK}}.
- Validate all incoming data at the API boundary before it reaches the Application layer.
