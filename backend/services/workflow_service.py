import os
import json
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import logging
from typing import Optional, List, Dict
import uuid

# Import all services and models
from models import WorkflowModel, PendingApprovalModel, KnowledgeBaseModel
from services.translation_service import TranslationService
from services.gemini_agent_service import GeminiAgentService
from services.knowledge_base_service import KnowledgeBaseService
from services.document_parser import DocumentParser

executor = ThreadPoolExecutor(max_workers=4)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class WorkflowService:
    """
    Main service for orchestrating the BOM processing workflow.
    It handles file uploads, document processing, data classification, and results storage.
    """
    def __init__(self):
        self.upload_dir = 'uploads'
        self.results_dir = 'results'
        self.translation_service = TranslationService()
        self.gemini_service = GeminiAgentService()
        self.kb_service = KnowledgeBaseService(gemini_service=self.gemini_service)
        self.doc_parser = DocumentParser()

    def start_workflow(self, workflow_id, workflow_name, wi_document, item_master=None, comparison_mode='full'):
        """
        Initializes and starts an asynchronous workflow.
        """
        try:
            workflow_dir = os.path.join(self.upload_dir, workflow_id)
            os.makedirs(workflow_dir, exist_ok=True)
            
            wi_path = os.path.join(workflow_dir, wi_document.filename)
            # Handle cases where wi_document is a real file or a mock object
            if hasattr(wi_document.file, 'read'):
                with open(wi_path, "wb") as buffer:
                    shutil.copyfileobj(wi_document.file, buffer)
            else:
                 shutil.copy(wi_document.file.name, wi_path)


            item_path = None
            if item_master:
                item_path = os.path.join(workflow_dir, item_master.filename)
                with open(item_path, "wb") as buffer:
                    shutil.copyfileobj(item_master.file, buffer)
            
            WorkflowModel.create_workflow(workflow_id, workflow_name, comparison_mode, wi_path, item_path)
            executor.submit(self._process_workflow_async, workflow_id, wi_path, item_path, comparison_mode)
            
            return True
        except Exception as e:
            logging.error(f"Failed to start workflow: {str(e)}")
            raise Exception(f"Failed to start workflow: {str(e)}")

    def _process_workflow_async(self, workflow_id, wi_path, item_path, comparison_mode):
        """
        The main asynchronous workflow execution loop.
        """
        try:
            WorkflowModel.update_workflow_status(
                workflow_id, 'processing', progress=10, 
                stage='extracting', message='Extracting data from documents'
            )
            
            wi_content = self.doc_parser.extract_text(wi_path)
            item_master_items = self.doc_parser.parse_item_master(item_path, self.gemini_service) if item_path else []
            kb_items = self.kb_service.get_items()
            
            logging.info(f"Workflow {workflow_id}: Document content extracted.")

            WorkflowModel.update_workflow_status(
                workflow_id, 'processing', progress=30, 
                stage='translating', message='Translating document to English'
            )
            
            translated_wi_content = self.translation_service.translate_to_english(wi_content)
            logging.info(f"Workflow {workflow_id}: Document translated.")

            WorkflowModel.update_workflow_status(
                workflow_id, 'processing', progress=50, 
                stage='classifying', message='Classifying and matching items with Gemini'
            )

            # Pass the extracted and standardized item master data to the classification logic
            extracted_items = self.gemini_service.extract_and_classify_items(
                document_content=translated_wi_content,
                item_master_content=json.dumps(item_master_items, indent=2),
                kb_items_content=json.dumps(kb_items, indent=2)
            )
            
            logging.info(f"Workflow {workflow_id}: Gemini agent completed. Extracted {len(extracted_items)} items.")
            
            # Deduplicate items before further processing
            deduplicated_items = self._deduplicate_items(extracted_items)

            # Separate items based on action path for different processing flows
            items_to_auto_register = []
            items_for_human_review = []
            for item in deduplicated_items:
                if item.get('action_path') == '🟢 Auto-Register':
                    items_to_auto_register.append(item)
                else:
                    items_for_human_review.append(item)
            
            # Process auto-register items
            if items_to_auto_register:
                self._add_to_knowledge_base(workflow_id, items_to_auto_register)
                logging.info(f"Workflow {workflow_id}: Auto-registered {len(items_to_auto_register)} items.")

            # Create pending approvals for human review items
            if items_for_human_review:
                self._create_pending_approvals(workflow_id, items_for_human_review)
                logging.info(f"Workflow {workflow_id}: Created {len(items_for_human_review)} pending approvals.")
            
            summary = self._generate_summary(deduplicated_items, comparison_mode)
            self._save_workflow_results(workflow_id, deduplicated_items, summary)
            
            WorkflowModel.update_workflow_status(
                workflow_id, 'completed', progress=100, 
                stage='completed', message='Processing completed successfully'
            )
            
        except Exception as e:
            WorkflowModel.update_workflow_status(
                workflow_id, 'error', message=f'Processing failed: {str(e)}'
            )
            logging.error(f"Workflow {workflow_id} failed with error: {e}")

    def _deduplicate_items(self, items: List[Dict]) -> List[Dict]:
        """
        Deduplicates a list of extracted items by merging duplicates based on material_name and part_number.
        """
        if not items:
            return []
            
        unique_items = {}
        for item in items:
            # Use .get() with a default empty string to handle missing keys gracefully
            material_name = item.get('material_name')
            part_number = item.get('part_number')
            
            # Check for None explicitly before calling .strip()
            material_name_str = material_name.strip() if material_name is not None else ''
            part_number_str = part_number.strip() if part_number is not None else ''
            
            key = f"{material_name_str.lower()}||{part_number_str.lower()}"
            
            if key in unique_items:
                # Merge logic: combine information from duplicate entries
                existing_item = unique_items[key]
                
                # Consolidate reasoning
                new_reasoning = item.get('reasoning', '')
                if new_reasoning and new_reasoning not in existing_item.get('reasoning', ''):
                    existing_item['reasoning'] = f"{existing_item.get('reasoning', '')} | {new_reasoning}"
                
                # Update confidence score (e.g., take the highest)
                existing_item['confidence_score'] = max(
                    existing_item.get('confidence_score', 0),
                    item.get('confidence_score', 0)
                )
                
                # Update action path (e.g., take the most conservative)
                action_path_priority = {
                    '🔴 Human Intervention Required': 3,
                    '🟠 Auto w/ Flag': 2,
                    '🟢 Auto-Register': 1
                }
                current_priority = action_path_priority.get(existing_item.get('action_path'))
                new_priority = action_path_priority.get(item.get('action_path'))
                
                if new_priority is not None and (current_priority is None or new_priority > current_priority):
                    existing_item['action_path'] = item.get('action_path')
                
                # Optionally, consolidate other fields like qa_classification_label
                if item.get('qa_classification_label') and item.get('qa_classification_label') != existing_item.get('qa_classification_label'):
                    existing_item['qa_classification_label'] = existing_item.get('qa_classification_label')
            else:
                unique_items[key] = item
                
        return list(unique_items.values())

    def _add_to_knowledge_base(self, workflow_id, matches):
        for match in matches:
            if isinstance(match, dict):
                KnowledgeBaseModel.add_item(
                    material_name=match.get('material_name'),
                    part_number=match.get('part_number'),
                    description=match.get('reasoning'),
                    classification_label=match.get('qa_classification_label'),
                    confidence_level=str(match.get('confidence_score')),
                    supplier_info=json.dumps({'vendor_name': match.get('vendor_name')}),
                    workflow_id=workflow_id,
                    approved_by='system',
                    metadata=json.dumps(match)
                )

    def _create_pending_approvals(self, workflow_id, matches):
        for match in matches:
            if isinstance(match, dict):
                PendingApprovalModel.add_pending_item(workflow_id, json.dumps(match))
    
    def get_workflow_status(self, workflow_id):
        workflow = WorkflowModel.get_workflow(workflow_id)
        if not workflow:
            raise ValueError("Workflow not found")
        return workflow
    
    def get_workflow_results(self, workflow_id):
        results_file = os.path.join(self.results_dir, f'{workflow_id}.json')
        if not os.path.exists(results_file):
            # Fallback to database
            conn = WorkflowModel.get_db_connection()
            result_row = conn.execute('SELECT results_data, summary_data FROM workflow_results WHERE workflow_id = ?', (workflow_id,)).fetchone()
            conn.close()
            if result_row:
                return {'matches': json.loads(result_row['results_data'])['matches'], 'summary': json.loads(result_row['summary_data'])}
            raise ValueError("Results not found")
        
        with open(results_file, 'r') as f:
            return json.load(f)

    def update_workflow_results(self, workflow_id: str, updated_data: Dict):
        """Saves the updated results to the JSON file and database."""
        self._save_workflow_results(workflow_id, updated_data['matches'], updated_data['summary'], overwrite=True)
        logging.info(f"Successfully updated results for workflow ID: {workflow_id}")

    
    def get_all_workflows(self):
        workflows = WorkflowModel.get_all_workflows()
        
        for workflow in workflows:
            results_file = os.path.join(self.results_dir, f"{workflow['id']}.json")
            workflow['has_results'] = os.path.exists(results_file)
        
        return workflows
        
    def _generate_summary(self, items, comparison_mode):
        if not isinstance(items, list):
            return {
                'total_materials': 0,
                'successful_matches': 0,
                'knowledge_base_matches': 0,
                'comparison_mode': comparison_mode
            }
        
        total_materials = len(items)
        successful_matches = sum(1 for item in items if isinstance(item, dict) and item.get('action_path') == '🟢 Auto-Register')
        knowledge_base_matches = 0
        
        return {
            'total_materials': total_materials,
            'successful_matches': successful_matches,
            'knowledge_base_matches': knowledge_base_matches,
            'comparison_mode': comparison_mode
        }

    def _save_workflow_results(self, workflow_id, results, summary, overwrite=False):
        results_file = os.path.join(self.results_dir, f'{workflow_id}.json')
        with open(results_file, 'w') as f:
            json.dump({'matches': results, 'summary': summary}, f, indent=2)
        
        from models import get_db_connection
        conn = get_db_connection()
        if overwrite:
             conn.execute('''
                UPDATE workflow_results SET results_data = ?, summary_data = ?
                WHERE workflow_id = ?
            ''', (json.dumps({'matches': results}), json.dumps(summary), workflow_id))
        else:
            conn.execute('''
                INSERT INTO workflow_results (workflow_id, results_data, summary_data)
                VALUES (?, ?, ?)
            ''', (workflow_id, json.dumps({'matches': results}), json.dumps(summary)))
        conn.commit()
        conn.close()

    def delete_workflow(self, workflow_id: str):
        """
        Deletes a workflow, its associated records, and all related files.
        """
        try:
            # Delete database records
            WorkflowModel.delete_workflow(workflow_id)
            WorkflowModel.delete_workflow_results(workflow_id)
            PendingApprovalModel.delete_pending_items_by_workflow(workflow_id)

            # Delete related files from disk
            workflow_dir = os.path.join(self.upload_dir, workflow_id)
            if os.path.exists(workflow_dir):
                shutil.rmtree(workflow_dir)
            
            results_file = os.path.join(self.results_dir, f'{workflow_id}.json')
            if os.path.exists(results_file):
                os.remove(results_file)
            
            logging.info(f"Successfully deleted workflow and files for ID: {workflow_id}")
            return {'success': True}
        except Exception as e:
            logging.error(f"Failed to delete workflow {workflow_id}: {str(e)}")
            raise Exception(f"Failed to delete workflow: {str(e)}")

    def download_files_from_cloud(self, url: str) -> List[Dict]:
        """
        Placeholder function to simulate downloading files from a cloud storage URL.
        In a real application, this would use the appropriate SDK (e.g., for
        SharePoint or Google Drive) to authenticate and download files.
        
        Returns a list of dicts, with each dict containing 'filename' and 'path'.
        """
        logging.info(f"Simulating download from cloud URL: {url}")
        
        # --- Integration Point for Cloud SDKs ---
        # Example for SharePoint using MSAL:
        # 1. Use MSAL to get an access token.
        # 2. Use the Microsoft Graph API with the token to list and download files.
        
        # Example for Google Drive:
        # 1. Use Google API Client Library for Python to authenticate (OAuth2).
        # 2. Use the Drive API to list and download files from the folder.
        
        # For demonstration, we'll create a couple of dummy files.
        simulated_dir = os.path.join(self.upload_dir, 'simulated_batch')
        os.makedirs(simulated_dir, exist_ok=True)
        
        files_to_create = {
            "WI_document_batch_1.txt": "This is a test WI document.",
            "QC_document_batch_2.txt": "This is a test QC document."
        }
        
        downloaded_files = []
        for filename, content in files_to_create.items():
            file_path = os.path.join(simulated_dir, filename)
            with open(file_path, 'w') as f:
                f.write(content)
            downloaded_files.append({'filename': filename, 'path': file_path})
            
        return downloaded_files
