import unittest
from unittest.mock import MagicMock
from backend.services.gemini_agent_service import GeminiAgentService
from backend.services.workflow_service import WorkflowService

class TestAgentLogic(unittest.TestCase):
    def setUp(self):
        # Mock Gemini API responses for consistent testing
        self.gemini_service = GeminiAgentService()
        self.gemini_service._call_api = MagicMock()
        
        # Initialize WorkflowService with the mock Gemini service
        self.workflow_service = WorkflowService()
        self.workflow_service.gemini_service = self.gemini_service
        self.workflow_service.kb_service.gemini_service = self.gemini_service

        # Mock knowledge base items for testing
        self.kb_items = [
            {'part_number': 'PN-123', 'material_name': 'Screw M3x10', 'lifecycle_status': 'Active'},
            {'part_number': 'PN-456', 'material_name': 'Hex Wrench 10mm', 'lifecycle_status': 'Active'},
            {'part_number': 'OBSOLETE-PN', 'material_name': 'Old Gasket', 'lifecycle_status': 'Obsolete'},
            {'part_number': 'PN-789', 'material_name': 'Kit A', 'lifecycle_status': 'Active', 'is_kit': True}
        ]
        
        self.workflow_service.kb_service.get_items = MagicMock(return_value=self.kb_items)
        
        # Mock item master for testing
        self.item_master_items = [
            {'part_number': 'PN-123', 'material_name': 'Screw M3x10'},
            {'part_number': 'PN-456', 'material_name': 'Hex Wrench 10mm'}
        ]

    def test_r001_perfect_match(self):
        """Test Rule R001: Green - Perfect Match"""
        extracted_item = {
            'material_name': 'Screw M3x10',
            'part_number': 'PN-123',
            'qty': '10',
            'vendor_name': 'Fasteners Inc.'
        }
        
        self.gemini_service.find_best_match.return_value = {
            'part_number': 'PN-123',
            'material_name': 'Screw M3x10',
            'lifecycle_status': 'Active',
            'confidence_score': 0.95
        }
        
        classified_item = self.workflow_service._apply_classification_logic(extracted_item, self.item_master_items)
        
        self.assertEqual(classified_item['qa_classification_label'], '1')
        self.assertEqual(classified_item['qa_confidence_level'], 'high')
        self.assertEqual(classified_item['action_path'], '🟢 Auto-Register')
        self.assertAlmostEqual(classified_item['confidence_score'], 0.95)

    def test_r002_fuzzy_kb_match_orange(self):
        """Test Rule R002: Orange - Fuzzy/No Master Match, but KB match"""
        extracted_item = {
            'material_name': 'Hex Wrench 10mm',
            'part_number': 'PN-456',
            'qty': '1',
            'vendor_name': ''
        }
        
        self.gemini_service.find_best_match.return_value = {
            'part_number': 'PN-456',
            'material_name': 'Hex Wrench 10mm',
            'lifecycle_status': 'Active',
            'confidence_score': 0.70
        }

        # Item is not in the item master for this test
        classified_item = self.workflow_service._apply_classification_logic(extracted_item, [])

        self.assertEqual(classified_item['qa_classification_label'], '4')
        self.assertEqual(classified_item['qa_confidence_level'], 'medium')
        self.assertEqual(classified_item['action_path'], '🟠 Auto w/ Flag')
        self.assertAlmostEqual(classified_item['confidence_score'], 0.70)
        
    def test_r003_new_item_orange(self):
        """Test Rule R003: Orange - New item detected"""
        extracted_item = {
            'material_name': 'New Gasket Material',
            'part_number': 'PN-999',
            'qty': '5',
            'vendor_name': 'Vendor XYZ'
        }
        
        self.gemini_service.find_best_match.return_value = None
        
        classified_item = self.workflow_service._apply_classification_logic(extracted_item, self.item_master_items)

        self.assertEqual(classified_item['qa_classification_label'], '4')
        self.assertEqual(classified_item['qa_confidence_level'], 'medium')
        self.assertEqual(classified_item['action_path'], '🟠 Auto w/ Flag')
        self.assertAlmostEqual(classified_item['confidence_score'], 0.60)

    def test_r004_obsolete_red(self):
        """Test Rule R004: Red - Obsolete part number"""
        extracted_item = {
            'material_name': 'Old Gasket',
            'part_number': 'OBSOLETE-PN',
            'qty': '1',
            'vendor_name': 'Old Parts Co.'
        }
        
        self.gemini_service.find_best_match.return_value = {
            'part_number': 'OBSOLETE-PN',
            'material_name': 'Old Gasket',
            'lifecycle_status': 'Obsolete',
            'confidence_score': 0.85
        }
        
        classified_item = self.workflow_service._apply_classification_logic(extracted_item, self.item_master_items)

        self.assertEqual(classified_item['qa_classification_label'], '7')
        self.assertEqual(classified_item['qa_confidence_level'], 'low')
        self.assertEqual(classified_item['action_path'], '🔴 Human Intervention Required')
        self.assertAlmostEqual(classified_item['confidence_score'], 0.20)

    def test_r005_extraction_failed_red(self):
        """Test Rule R005: Red - Extraction failed"""
        extracted_item = {
            'material_name': '',
            'part_number': '',
            'qty': '',
            'vendor_name': ''
        }
        
        self.gemini_service.find_best_match.return_value = None
        
        classified_item = self.workflow_service._apply_classification_logic(extracted_item, self.item_master_items)
        
        self.assertEqual(classified_item['qa_classification_label'], '5')
        self.assertEqual(classified_item['qa_confidence_level'], 'low')
        self.assertEqual(classified_item['action_path'], '🔴 Human Intervention Required')
        self.assertAlmostEqual(classified_item['confidence_score'], 0.10)

if __name__ == '__main__':
    unittest.main()