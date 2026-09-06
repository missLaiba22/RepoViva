# Requirements

## Goal

Help developers practise explaining and defending their own
GitHub projects through a realistic, code-aware mock interview.

## Functional Requirements

### Repository
- User can connect/provide a GitHub repository.
- System can fetch the repository.
- System can process and analyze the repository.
- System can create a searchable/code-aware representation of the project.

### Interview
- User can start a mock interview for a repository.
- System asks questions based on the user's actual code.
- User can answer using voice.
- System can understand the user's answer.
- System can ask relevant follow-up questions.
- Interview maintains conversation context.

### Evaluation
- System evaluates the user's answers.
- Evaluation considers technical correctness and explanation quality.
- User receives a final interview report.

## Non-Functional Requirements

- Interview interaction should feel reasonably responsive.
- Repository processing should not block the user's normal API requests.
- User repositories and interview data must be isolated and protected.
- The system should be able to handle repositories of different sizes.
- AI-generated questions and evaluations should be grounded in the user's repository rather than generic assumptions.

## MVP Scope

- GitHub repository ingestion
- Repository/code analysis
- Code-aware retrieval
- Code-specific interview questions
- Voice-based interview
- Follow-up questions
- Answer evaluation
- Final report

## Out of Scope

- Multi-user enterprise/team features
- Complex microservice architecture
- A2A communication
- Multiple specialized AI agents unless a real requirement emerges
- Advanced scaling infrastructure
- Supporting every possible Git hosting provider