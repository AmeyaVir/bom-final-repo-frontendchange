import os
import json
import uuid
import logging
from typing import Optional, List, Dict

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel

from services.workflow_service import WorkflowService
from services.knowledge_base_service import KnowledgeBaseService
from models import ItemApprovalRequest

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI(
    title="BOM Platform API",
    description="Backend API for the autonomous BOM processing platform with Gemini integration.",
    version="4.2.0",
)

# Configure CORS
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class URLUploadRequest(BaseModel):
    url: str
    workflow_name: str

class UpdateResultsRequest(BaseModel):
    matches: List[Dict]
    summary: Dict

# Add a custom exception handler for validation errors to get detailed logs
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logging.error(f"Validation Error: {exc.errors()} for request to {request.url}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

@app.on_event("startup")
async def startup_event():
    """Initializes the database and creates directories on startup."""
    try:
        from models import init_db
        init_db()
        os.makedirs(workflow_service.upload_dir, exist_ok=True)
        os.makedirs(workflow_service.results_dir, exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server startup failed: {e}")

# Initialize services
workflow_service = WorkflowService()
kb_service = KnowledgeBaseService()

# --- Cloud Authentication Endpoints ---

@app.get("/api/auth/sharepoint/start")
async def auth_sharepoint_start():
    """
    Placeholder to start the SharePoint OAuth2 flow.
    In a real app, this would redirect the user to Microsoft's login page.
    """
    # TODO: Implement MSAL logic to build the authorization URL
    # from msal import ConfidentialClientApplication
    # app = ConfidentialClientApplication(client_id, authority=authority, client_credential=secret)
    # auth_url = app.get_authorization_request_url(scopes)
    # return RedirectResponse(auth_url)
    return JSONResponse(content={"message": "SharePoint auth flow starts here. Redirect to Microsoft login."})

@app.get("/api/auth/gdrive/start")
async def auth_gdrive_start():
    """
    Placeholder to start the Google Drive OAuth2 flow.
    In a real app, this would redirect the user to Google's login page.
    """
    # TODO: Implement Google Auth logic to build the authorization URL
    # from google_auth_oauthlib.flow import Flow
    # flow = Flow.from_client_secrets_file('client_secrets.json', scopes=scopes)
    # authorization_url, state = flow.authorization_url()
    # return RedirectResponse(authorization_url)
    return JSONResponse(content={"message": "Google Drive auth flow starts here. Redirect to Google login."})


@app.get("/api/workflows")
async def get_workflows():
    """Get all workflows from the database."""
    try:
        workflows = workflow_service.get_all_workflows()
        return JSONResponse(content={'success': True, 'workflows': workflows})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str):
    """Deletes a workflow and all associated data."""
    try:
        workflow_service.delete_workflow(workflow_id)
        return JSONResponse(content={'success': True, 'message': f'Workflow {workflow_id} deleted successfully'})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/knowledge-base")
async def get_knowledge_base(search: Optional[str] = "", limit: int = 50):
    """Get knowledge base items with statistics, with optional search."""
    try:
        items = kb_service.get_items(search, limit)
        stats = kb_service.get_stats()
        return JSONResponse(content={'success': True, 'items': items, 'stats': stats})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/knowledge-base/pending")
async def get_pending_approvals():
    """Get pending items for approval."""
    try:
        pending_items = kb_service.get_pending_approvals()
        return JSONResponse(content={'success': True, 'pending_items': pending_items})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/knowledge-base/approve")
async def approve_knowledge_base_item(request: ItemApprovalRequest):
    """Approve an item for the knowledge base."""
    try:
        logging.info(f"Received approval request for items: {request.item_ids} from workflow: {request.workflow_id}")
        result = kb_service.approve_items(request.item_ids)
        return JSONResponse(content={'success': True, 'approved_count': result})
    except Exception as e:
        logging.error(f"Error approving items: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/knowledge-base/reject")
async def reject_knowledge_base_item(request: ItemApprovalRequest):
    """Reject an item from the knowledge base."""
    try:
        logging.info(f"Received rejection request for items: {request.item_ids} from workflow: {request.workflow_id}")
        result = kb_service.reject_items(request.item_ids)
        return JSONResponse(content={'success': True, 'rejected_count': result})
    except Exception as e:
        logging.error(f"Error rejecting items: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/knowledge-base/{item_id}")
async def delete_knowledge_base_item(item_id: int):
    """Delete an item from the knowledge base."""
    try:
        kb_service.delete_item(item_id)
        return JSONResponse(content={'success': True, 'message': 'Item deleted successfully'})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/autonomous/upload")
async def upload_documents(
    wi_document: UploadFile = File(..., description="The WI/QC document to process."),
    workflow_name: str = Form(..., description="A user-defined name for the workflow."),
    item_master: Optional[UploadFile] = File(None, description="Optional Item Master for full comparison mode."),
    comparison_mode: str = Form(..., description="'full' or 'kb_only'")
):
    """Handles single document upload with a user-defined workflow name."""
    try:
        if not wi_document:
            raise HTTPException(status_code=400, detail="WI document is required")

        if comparison_mode == 'full' and not item_master:
            raise HTTPException(status_code=400, detail="Item Master is required for full comparison mode")

        workflow_id = str(uuid.uuid4())

        # Start processing asynchronously
        workflow_service.start_workflow(
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            wi_document=wi_document,
            item_master=item_master,
            comparison_mode=comparison_mode
        )

        return JSONResponse(content={
            'success': True,
            'workflow_id': workflow_id,
            'message': 'Processing started successfully'
        })
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start workflow: {str(e)}")

@app.post("/api/autonomous/upload_from_url")
async def upload_from_url(request: URLUploadRequest):
    """
    Handles document processing from a cloud storage URL (Sharepoint, GDrive).
    This endpoint simulates downloading files and starting batch workflows.
    """
    try:
        # In a real implementation, you would use a cloud-specific SDK
        # to authenticate and download the files from the provided URL.
        # This is a placeholder for that logic.
        downloaded_files = workflow_service.download_files_from_cloud(request.url)

        if not downloaded_files:
            raise HTTPException(status_code=400, detail="Could not retrieve files from the provided URL.")

        workflow_ids = []
        # Process each downloaded file as a separate workflow
        for file_info in downloaded_files:
            workflow_id = str(uuid.uuid4())
            
            # Here we are simulating the file objects that FastAPI creates
            class MockUploadFile:
                def __init__(self, filename, file_path):
                    self.filename = filename
                    self.file = open(file_path, 'rb')

            wi_doc = MockUploadFile(file_info['filename'], file_info['path'])

            # Determine workflow type based on filename
            workflow_type = "WI" if "wi" in file_info['filename'].lower() else "QC"
            workflow_name = f"{request.workflow_name} - {workflow_type} - {file_info['filename']}"

            workflow_service.start_workflow(
                workflow_id=workflow_id,
                workflow_name=workflow_name,
                wi_document=wi_doc,
                comparison_mode='kb_only' # Assuming kb_only for batch processing
            )
            workflow_ids.append(workflow_id)

        return JSONResponse(content={
            'success': True,
            'workflow_ids': workflow_ids,
            'message': f'Started batch processing for {len(workflow_ids)} documents.'
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start batch workflow: {str(e)}")


@app.get("/api/autonomous/workflow/{workflow_id}/status")
async def get_workflow_status(workflow_id: str):
    """Get workflow status."""
    try:
        status = workflow_service.get_workflow_status(workflow_id)
        return JSONResponse(content=status)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {str(e)}")

@app.get("/api/autonomous/workflow/{workflow_id}/results")
async def get_workflow_results(workflow_id: str):
    """Get workflow results."""
    try:
        results = workflow_service.get_workflow_results(workflow_id)
        return JSONResponse(content=results)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Results not found: {str(e)}")

@app.post("/api/autonomous/workflow/{workflow_id}/results")
async def update_workflow_results(workflow_id: str, request: UpdateResultsRequest):
    """Update workflow results after user edits."""
    try:
        workflow_service.update_workflow_results(workflow_id, request.dict())
        return JSONResponse(content={'success': True, 'message': 'Results updated successfully'})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update results: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

