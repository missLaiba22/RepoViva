# RepoViva

## What is RepoViva?

RepoViva is a voice-based interview coach for developers. A user connects a GitHub repository, RepoViva studies the actual code in the project, and then conducts a realistic technical interview based on that code.

It asks questions, listens to spoken answers, can ask follow-up questions, evaluates the answers, and produces a report at the end.

## Problem

Developers often prepare for technical interviews using generic questions, but they may struggle to explain and defend the projects they have actually built.

RepoViva helps developers practise discussing their own code before a real interview.

## How it works

1. User connects a GitHub repository.
2. RepoViva fetches and analyzes the repository.
3. The system builds a code-aware representation that can be used to retrieve relevant parts of the project.
4. User starts a mock interview.
5. RepoViva asks questions grounded in the user's actual project.
6. User answers using voice.
7. RepoViva can ask follow-up questions based on the conversation and code.
8. The system evaluates the answers.
9. User receives a report with feedback.

## MVP

* Connect a GitHub repository.
* Fetch and process repository code.
* Analyze the project's structure and code.
* Retrieve relevant code for interview questions.
* Conduct a code-aware mock interview.
* Support spoken questions and answers.
* Evaluate interview answers.
* Generate an interview report.

## Tech Stack

* Frontend: React
* Backend: FastApi
* Database: TBD
* AI / LLM: TBD
* Code analysis / retrieval: TBD
* Voice: TBD
* Infrastructure: TBD

## Project Status

Currently in the planning and architecture phase.
