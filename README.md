# Final Project

# CanvasGPT: Intelligent Canvas Management Assistant

### Goal of the Project
- Automate routine administrative tasks in Canvas LMS to reduce time burden
- Implement intelligent content organization across course sections
- Streamline creation and management of course announcements
- Optimize grading workflow efficiency
- Enhance content discovery and reusability
- Process and integrate academic materials from research databases
- Improve overall teaching productivity through AI assistance

### Project Overview
CanvasGPT is an innovative AI-powered application designed to transform how professors interact with Canvas Learning Management System (LMS). The system leverages advanced natural language processing to automate course management tasks, process academic materials from SpringerLink Research database, and provide an intuitive chat interface for professors to efficiently manage their courses. Through integrated AI capabilities, secure data management, and automated workflows, CanvasGPT serves as a personal Canvas assistant, enabling educators to focus more on teaching and student engagement rather than administrative tasks.

### Key Technologies Involved

- **Chrome Extension**: Custom UI development for direct Canvas integration and chat interface
- **Streamlit**: Admin dashboard development for monitoring and analytics
- **FastAPI**: High-performance REST API development with async support
- **OpenAI Models**: Natural language processing and document understanding
- **Azure Cloud Storage**: Secure file storage and document management
- **Snowflake DB**: Structured data storage for course and user information
- **Pinecone**: Vector database for semantic search and document retrieval
- **Docling**: Parsing documents and extracting structured information. 
- **Apache Airflow**: Orchestration of ETL pipelines and scheduling tasks
- **LlamaParser**: Document parsing and text extraction from various formats
- **Docker**: Application containerization and environment standardization
- **Git Actions**: CI/CD pipeline automation and testing
- **GitLab**: Version control and project management
- **Langraph**: Conversation flow management and dialogue state handling
- **NV-Embed Embeddings**: Document vectorization for semantic search
- **HTML/CSS**: Frontend styling and layout
- **JavaScript**: Client-side functionality and Canvas API integration 

## Project Resources

Google codelab: []

Google collab notebook: []

### Architecture diagram ###

![image](Architecture/images/cfa_architecture_diag.png)


### Deployment
The system is deployed on **Google Cloud Platform (GCP)**, using Docker for containerized deployment:
- **Docker**: Containers manage FastAPI and Streamlit, with Docker Compose orchestrating the components for consistent deployment.
- **GCP**: Ensures public access to the application and scalable infrastructure to accommodate user demand.


### Additional Notes
WE ATTEST THAT WE HAVEN’T USED ANY OTHER STUDENTS’ WORK IN OUR ASSIGNMENT AND ABIDE BY THE POLICIES LISTED IN THE STUDENT HANDBOOK. 







