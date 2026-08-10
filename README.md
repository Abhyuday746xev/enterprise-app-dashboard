Enterprise App Dashboard

A full-stack enterprise management dashboard that integrates Microsoft Intune / Microsoft Graph, MySQL, ChromaDB, and a local LLM to provide synchronized enterprise data, Retrieval-Augmented Generation (RAG), and live Intune information retrieval.

The current AI implementation is intentionally read-oriented: it can retrieve, search, summarize, and explain enterprise information, but it does not autonomously execute Microsoft Graph administrative actions.

Features

Enterprise Dashboard

View synchronized Microsoft Intune applications

View managed devices

View enterprise users

Display device compliance and last-sync information

Display application metadata and publishing information

Central Flask API for frontend access

Microsoft Graph / Intune Integration

Retrieves enterprise data from Microsoft Graph

Synchronizes Graph data into MySQL

Supports live Microsoft Intune retrieval for current inventory questions

Separates live Graph retrieval from locally synchronized data

Local Enterprise AI

Local LLM-based enterprise assistant

Retrieval-Augmented Generation (RAG)

ChromaDB vector database

Semantic search over enterprise data

Live Intune query routing

Conversation memory support

Enterprise-specific prompt construction

Ticket Management

Ticket-management functionality exposed through a Flask blueprint

Integrated into the same backend application

Protected Control Panel

Separate administrative Control Panel

Kept logically separate from the Local LLM

AI does not directly execute Control Panel actions

Current AI Architecture

The Local LLM currently has two information paths.

1. Live Intune Retrieval

Used when a question requires current Microsoft Graph / Intune information.

User Question
     |
     v
/api/ask
     |
     v
live_query_router.py
     |
     v
live_intune_tools.py
     |
     v
Microsoft Graph
     |
     v
Live Enterprise Answer

Typical examples:

Find user john@company.com
Show information about device MACBOOK-01
Find Microsoft Teams
Show information about Adobe Acrobat

2. RAG Retrieval

Used when the question is better answered from the enterprise knowledge base.

User Question
     |
     v
/api/ask
     |
     v
rag_pipeline.py
     |
     v
retriever.py
     |
     v
ChromaDB
     |
     v
Relevant Enterprise Context
     |
     v
Local LLM
     |
     v
Generated Answer

Typical examples:

What applications do we have?
Summarize our managed devices.
What software is published by Microsoft?
What do we know about Adobe applications?

Data Synchronization Pipeline

The project maintains both structured MySQL data and an AI-searchable ChromaDB knowledge base.

Microsoft Graph
      |
      v
 batch_sync.py
      |
      v
    MySQL
      |
      v
local_llm.ingest
      |
      v
 Chunking
      |
      v
 Embeddings
      |
      v
  ChromaDB

The backend exposes:

POST /api/sync

This performs:

Microsoft Graph → MySQL synchronization

MySQL → ChromaDB knowledge-base ingestion

A synchronization lock prevents two sync jobs from running simultaneously in the same Flask process.

Project Structure

enterprise-app-dashboard/
|
|-- backend/
|   |-- app.py
|   |-- batch_sync.py
|   |-- database.py
|   |-- ticket_service.py
|   |-- .env.example
|   |
|   |-- control_panel/
|   |   `-- ...
|   |
|   `-- local_llm/
|       |-- __init__.py
|       |-- chunker.py
|       |-- config.py
|       |-- embeddings.py
|       |-- ingest.py
|       |-- live_intune_tools.py
|       |-- live_query_router.py
|       |-- llm.py
|       |-- memory.py
|       |-- models.py
|       |-- prompts.py
|       |-- rag_pipeline.py
|       |-- retriever.py
|       `-- vector_store.py
|
|-- frontend/
|   `-- ...
|
|-- requirements.txt
|-- .gitignore
`-- README.md

Backend API

Health

GET /api/health

Reports backend service status such as:

MySQL connectivity

Live Intune router availability

RAG availability

Control Panel availability

Applications

GET /api/apps

Returns synchronized Intune application information.

Devices

GET /api/devices

Returns managed-device information including:

Device name

User

Operating system

OS version

Manufacturer

Model

Compliance state

Last synchronization time

Users

GET /api/users

Returns enterprise user information including:

Display name

User principal name

Email

Mobile phone

Account-enabled state

Synchronization

POST /api/sync

Synchronizes:

Microsoft Graph -> MySQL -> ChromaDB

Enterprise AI

POST /api/ask

Example request:

{
  "question": "Show information about device MACBOOK-01"
}

The backend first attempts live Intune retrieval.

If the question is not handled by the live router, it falls back to the RAG pipeline.

Enterprise AI Routing

                       User Question
                            |
                            v
                        /api/ask
                            |
                            v
                  try_live_intune_query()
                            |
                 +----------+----------+
                 |                     |
              handled                not handled
                 |                     |
                 v                     v
        Microsoft Graph        ask_enterprise_ai()
                 |                     |
                 v                     v
        Live Intune Answer          ChromaDB
                                       |
                                       v
                                Retrieved Context
                                       |
                                       v
                                   Local LLM
                                       |
                                       v
                                   RAG Answer

The API response can identify the route used, for example:

{
  "route": "live_intune"
}

or:

{
  "route": "rag"
}

Local LLM Components

rag_pipeline.py

Coordinates the RAG question-answering workflow.

retriever.py

Retrieves semantically relevant enterprise records from ChromaDB.

vector_store.py

Handles the vector database.

embeddings.py

Generates vector embeddings for enterprise content and queries.

chunker.py

Breaks enterprise information into smaller searchable chunks.

ingest.py

Builds or updates the ChromaDB knowledge base from synchronized enterprise data.

prompts.py

Constructs enterprise-specific prompts for the local model.

llm.py

Provides access to the configured local language model.

memory.py

Maintains conversational context where supported.

live_query_router.py

Determines whether a question should use live Microsoft Graph / Intune retrieval.

live_intune_tools.py

Contains the read-oriented Microsoft Graph retrieval functions used by the live router.

Technology Stack

Backend

Python

Flask

Flask-CORS

Enterprise Integration

Microsoft Graph API

Microsoft Intune

Database

MySQL

AI / Retrieval

Local LLM

Retrieval-Augmented Generation

ChromaDB

Vector embeddings

Frontend

HTML

CSS

JavaScript

Development

Git

GitHub

Python virtual environment

Setup

1. Clone the repository

git clone https://github.com/YOUR_USERNAME/enterprise-app-dashboard.git
cd enterprise-app-dashboard

2. Create a virtual environment

python3 -m venv venv
source venv/bin/activate

3. Install dependencies

pip install -r requirements.txt

4. Create the backend environment file

cp backend/.env.example backend/.env

Then configure the required environment variables.

Example:

FLASK_SECRET_KEY=replace-me
FLASK_HOST=127.0.0.1
FLASK_PORT=5000
FLASK_DEBUG=true

CORS_ORIGINS=http://127.0.0.1:5500

DB_HOST=localhost
DB_PORT=3306
DB_NAME=enterprise_dashboard
DB_USER=your-user
DB_PASSWORD=your-password

TENANT_ID=your-tenant-id
CLIENT_ID=your-client-id
CLIENT_SECRET=your-client-secret

CONTROL_PANEL_API_KEY=replace-me

Use the exact variable names expected by your local database and Microsoft Graph configuration.

5. Start the backend

cd backend
python app.py

By default, the API is typically available at:

http://127.0.0.1:5000

6. Check backend health

curl http://127.0.0.1:5000/api/health

Example AI Queries

Live Intune Queries

Find user john@company.com
Show information about device MACBOOK-01
Find Microsoft Teams
Show information about Adobe Acrobat

RAG Queries

What applications do we have?
Summarize our managed-device information.
What software is published by Microsoft?
Tell me about our Windows devices.
What information do we have about Adobe applications?

Security

Never commit sensitive information to GitHub.

The repository .gitignore should exclude:

.env
backend/.env
venv/
.venv/
__pycache__/
local ChromaDB data
database files
logs

Do not commit:

Microsoft Graph client secrets

Microsoft Graph access tokens

Database passwords

Control Panel API keys

Tenant credentials

Private certificates

Production secrets

Use .env.example only for placeholder configuration values.

Current AI Safety Boundary

The Local LLM is currently an information and retrieval assistant.

It can:

Retrieve enterprise information

Search the local knowledge base

Query supported live Intune data

Summarize enterprise records

Explain retrieved information

Maintain conversational context where supported

It does not autonomously:

Restart devices

Synchronize devices

Enable or disable users

Assign applications

Remove application assignments

Delete applications

Execute arbitrary Microsoft Graph write operations

Perform automatic remediation

Administrative functionality remains separate from the Local LLM.

Current Development Status

Implemented:

Microsoft Graph / Intune integration

Graph-to-MySQL synchronization

MySQL-backed dashboard APIs

ChromaDB knowledge-base ingestion

Local LLM integration

Retrieval-Augmented Generation

Semantic enterprise search

Live Intune retrieval

AI live-query routing

Enterprise AI /api/ask endpoint

Ticket subsystem

Protected Control Panel subsystem

Health endpoint

CORS configuration

Future development may include:

Improved natural-language live-query routing

Better entity resolution

More advanced enterprise analytics

Richer source attribution

Authentication and role-based access

Persistent conversation history

Automated testing

Deployment and CI/CD

Carefully controlled AI-assisted remediation workflows

Development Workflow

After making changes:

git status
git add .
git diff --cached
git commit -m "Describe your changes"
git push

Always verify that .env and other secrets are ignored before committing.

License

Add the license appropriate for your project before public distribution.

Author

Abhyuday Tripathi

Enterprise App Dashboard — Microsoft Intune, Microsoft Graph, RAG, and Local LLM integration.
