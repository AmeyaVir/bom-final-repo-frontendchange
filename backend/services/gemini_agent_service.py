import os
import json
import requests
from typing import Optional, List, Dict
from dotenv import load_dotenv
import re
import time

load_dotenv()

class GeminiAgentService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")
        
        self.url = os.getenv("GEMINI_API_URL", "https://api.ai-gateway.tigeranalytics.com/chat/completions")
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    def _extract_json_from_markdown(self, text: str) -> str:
        """
        Extracts a JSON string from a Markdown code block.
        Returns an empty string if no JSON code block is found.
        """
        match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return match.group(1)
        return text

    def _call_api_with_retry(self, payload: Dict, max_retries: int = 5) -> requests.Response:
        """
        Internal helper to make a call to the external Gemini API gateway with exponential backoff.
        """
        for i in range(max_retries):
            try:
                response = requests.post(self.url, headers=self.headers, data=json.dumps(payload))
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429 and i < max_retries - 1:
                    wait_time = 2 ** i
                    print(f"Rate limit exceeded. Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    raise RuntimeError(f"API call failed after {i+1} retries: {e}")
            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"API call failed: {e}")
        return None

    def _call_api(self, prompt: str, response_mime_type: Optional[str] = None, temperature: float = 0.2) -> requests.Response:
        """
        Internal helper to make a call to the external Gemini API gateway.
        """
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature
        }
        
        # Pass response_mime_type in a nested generationConfig as per the API's documentation
        if response_mime_type:
            payload["generationConfig"] = {"responseMimeType": response_mime_type}

        return self._call_api_with_retry(payload)

    def extract_and_classify_items(self, document_content: str, item_master_content: str, kb_items_content: str) -> list:
        """
        Uses the LLM to extract, classify, and match auxiliary items from a document based on an item master and a knowledge base.
        Returns a single, valid JSON array of objects, with each object containing the attributes specified by the user.
        """
        user_prompt = f"""
        Analyze the provided document content (WI/QC) and extract all auxiliary items. For each item, classify it as 'Consumable', 'Jig', 'Tool', or 'Other'. Then, compare it against the provided item master data and knowledge base to find matches.

        Your task is to populate a JSON array of objects with the following attributes for each extracted item:
        - qc_process_or_wi_step: The specific step or action in the document where the item is mentioned.
        - item_type: The classification of the item ('Consumable', 'Jig', 'Tool', or 'Other').
        - material_name: The name of the material or item.
        - part_number: The part number.
        - qty: The quantity.
        - uom: The unit of measure (e.g., 'Litre', 'Number', 'Kg').
        - vendor_name: The vendor name.
        - qa_classification_label: The classification label from the predefined list (1, 2, 3, etc.).
        
        Additionally, based on your comparison with the item master and knowledge base, determine the following:
        - name_mismatch: 'true' if the material name does not match an item in the master.
        - pn_match: 'true' if the part number is an exact match in the master or KB.
        - pn_mismatch: 'true' if the part number exists but does not match the material name in the master.
        - obsolete_pn: 'true' if the part number is identified as obsolete.
        - kit_available: 'true' if the document mentions a pre-assembled kit.
        - reasoning: A brief explanation of your classification and matching decision.
        - confidence_score: A number from 0.0 to 1.0 representing the certainty of your classification and matching.
        - action_path: The recommended action based on the confidence level and rules (e.g., '🟢 Auto-Register', '🟠 Auto w/ Flag', '🔴 Human Intervention Required').

        Use the following table for guidance on reasoning and action paths. The rules are in descending order of priority.

        - If there is a part number match and a quantity:
            - **Reasoning:** "Item name, part number, and quantity match an item in the master data."
            - **Confidence:** High (0.95-1.0)
            - **Action Path:** 🟢 Auto-Register
        - If there is a part number match but no quantity:
            - **Reasoning:** "Item name and part number match an item in the master or KB, but no quantity is specified. Quantity needs to be inferred."
            - **Confidence:** Medium (0.60-0.80)
            - **Action Path:** 🟠 Auto w/ Flag
        - If a kit is mentioned:
            - **Reasoning:** "A pre-assembled kit is mentioned. It may require a review of the kit's Bill of Materials."
            - **Confidence:** Medium (0.50-0.70)
            - **Action Path:** 🟠 Auto w/ Flag
        - If there is a match based on vendor name only:
            - **Reasoning:** "Only the vendor name is present, but no part number or material name. The item needs to be mapped to a specific consumable."
            - **Confidence:** Medium (0.50-0.70)
            - **Action Path:** 🟠 Auto w/ Flag
        - If there is a part number mismatch or no part number, but a name match in the master or KB:
            - **Reasoning:** "Part number is not a match, or is not present. The item name matches, but requires human review to confirm the correct part."
            - **Confidence:** Low (0.20-0.40)
            - **Action Path:** 🔴 Human Intervention Required
        - If the part number is obsolete:
            - **Reasoning:** "The part number is identified as obsolete and requires a cross-check for a suitable replacement."
            - **Confidence:** Low (0.20-0.40)
            - **Action Path:** 🔴 Human Intervention Required
        - If the material name is ambiguous:
            - **Reasoning:** "The material name is ambiguous and may refer to multiple items. Human review is required to clarify."
            - **Confidence:** Low (0.20-0.40)
            - **Action Path:** 🔴 Human Intervention Required
        - Default case (no clear match):
            - **Reasoning:** "No match found in the item master or knowledge base. Requires human review."
            - **Confidence:** Very Low (0.0-0.2)
            - **Action Path:** 🔴 Human Intervention Required

        Document Content:
        {document_content}

        Item Master Content:
        {item_master_content}

        Knowledge Base Content:
        {kb_items_content}
        
        The output must be a single, valid JSON array of objects. Do not include any other text or formatting.
        """
        try:
            response = self._call_api(user_prompt, response_mime_type="application/json")
            raw_data = response.json()
            if 'choices' not in raw_data or not raw_data['choices']:
                print(f"API response missing 'choices': {raw_data}")
                return []
            extracted_text = raw_data['choices'][0]['message']['content']
            
            # Extract JSON string from markdown and then load it
            json_string = self._extract_json_from_markdown(extracted_text)
            parsed_data = json.loads(json_string)
            if isinstance(parsed_data, list):
                return parsed_data
            else:
                return []
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON response from API: {e}")
            print(f"Raw API Response: {response.text}")
            return []
        except Exception as e:
            print(f"Error calling Gemini API for item extraction: {e}")
            return []

    def check_obsolete_pn(self, part_number: str) -> bool:
        """
        Uses the LLM to check a part number against a hypothetical knowledge base for obsolescence status.
        Returns True if the LLM identifies it as obsolete, False otherwise.
        """
        user_prompt = f"""
        Based on public knowledge and industry standards, is the part number "{part_number}" commonly associated with an obsolete or discontinued status?
        Provide a concise response of only 'True' or 'False'.
        """
        try:
            response = self._call_api(user_prompt)
            if 'choices' not in response.json() or not response.json()['choices']:
                print(f"API response missing 'choices': {response.text}")
                return False
            extracted_text = response.json()['choices'][0]['message']['content']
            return extracted_text.strip().lower() == 'true'
        except Exception as e:
            print(f"Error calling Gemini API for obsolete check: {e}")
            return False

    def check_for_match(self, text_to_search: str, item_name: str, part_number: Optional[str] = None) -> bool:
        """
        Uses the LLM to check for a specific item name or part number match within a block of text.
        Returns True if a match is found, False otherwise.
        """
        user_prompt = f"""
        Does the following document text contain a reference to the item name "{item_name}"?
        The part number "{part_number}" might also be used.
        Respond with only 'True' or 'False'. Do not include any other text.

        Document text:
        {text_to_search}
        """
        try:
            response = self._call_api(user_prompt)
            if 'choices' not in response.json() or not response.json()['choices']:
                print(f"API response missing 'choices': {response.text}")
                return False
            extracted_text = response.json()['choices'][0]['message']['content']
            return extracted_text.strip().lower() == 'true'
        except Exception as e:
            print(f"Error calling Gemini API for match check: {e}")
            return False

    def extract_details(self, document_content: str, item_name: str) -> dict:
        """
        Uses the LLM to extract specific details like quantity and UoM for a given item name.
        """
        user_prompt = f"""
        From the following document content, extract the quantity (qty) and unit of measure (uom) for the item named "{item_name}".
        If a detail is not found, use a blank string.
        The output must be a valid JSON object with the keys "qty" and "uom".

        Document Content:
        {document_content}
        """
        try:
            response = self._call_api(user_prompt, response_mime_type="application/json")
            if 'choices' not in response.json() or not response.json()['choices']:
                print(f"API response missing 'choices': {response.text}")
                return {'qty': '', 'uom': ''}
            extracted_text = response.json()['choices'][0]['message']['content']

            # Extract JSON string from markdown and then load it
            json_string = self._extract_json_from_markdown(extracted_text)
            return json.loads(json_string)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON response from API: {e}")
            print(f"Raw API Response: {response.text}")
            return {'qty': '', 'uom': ''}
        except Exception as e:
            print(f"Error calling Gemini API for detail extraction: {e}")
            return {'qty': '', 'uom': ''}
            
    def standardize_item_master(self, csv_content: str) -> list:
        """
        Uses LLM to standardize column headers in a CSV string to a predefined format.
        """
        standard_columns = ["material_name", "part_number", "description", "vendor_name", "uom"]
        prompt = f"""
        Given the following CSV content, standardize the column names to match a predefined list.
        Map any equivalent columns (e.g., 'Item Code' to 'part_number'). If a column has no equivalent, ignore it.
        The output must be a single, valid JSON array of objects, with each object containing the standardized keys.
        
        Standard Columns: {standard_columns}
        
        CSV Content:
        {csv_content}
        
        Standardized JSON Array:
        """
        try:
            response = self._call_api(prompt, response_mime_type="application/json")
            if 'choices' not in response.json() or not response.json()['choices']:
                print(f"API response missing 'choices': {response.text}")
                return []
            extracted_text = response.json()['choices'][0]['message']['content']

            # Extract JSON string from markdown and then load it
            json_string = self._extract_json_from_markdown(extracted_text)
            standardized_data = json.loads(json_string)
            if isinstance(standardized_data, list):
                return standardized_data
            else:
                return []
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON response from API: {e}")
            print(f"Raw API Response: {response.text}")
            return []
        except Exception as e:
            print(f"Error standardizing item master with LLM: {e}")
            return []
            
    def find_best_match(self, extracted_item: Dict, kb_items: List[Dict]) -> Optional[Dict]:
        """
        Uses the LLM to find the best matching item from a list of knowledge base items,
        considering fuzzy part number, semantic material name, and other metadata.
        
        Args:
            extracted_item: The item extracted from the new document.
            kb_items: A list of candidate items from the knowledge base.
            
        Returns:
            The best matching knowledge base item with a confidence score, or None.
        """
        
        prompt = f"""
        You are a highly accurate inventory matching agent. Your task is to find the single best match from a list of candidate items for a new item.
        
        The new item to match is:
        - Part Number: {extracted_item.get('part_number', 'N/A')}
        - Material Name: {extracted_item.get('material_name', 'N/A')}
        - Description: {extracted_item.get('description', 'N/A')}
        - Vendor Name: {extracted_item.get('vendor_name', 'N/A')}
        
        The list of candidate items from the knowledge base is:
        {json.dumps(kb_items, indent=2)}
        
        Rules for matching:
        1. Prioritize an exact or very close fuzzy match on 'part_number'.
        2. If part numbers are not a strong match, use 'material_name' and 'description' to find a strong semantic match.
        3. 'vendor_name' is an important secondary piece of information for confirmation.
        4. If a strong match is found, return the full details of the best matching item from the list.
        5. If no confident match (e.g., more than one ambiguous match or no match at all) is found, return an empty JSON object.
        6. The response must be a single, valid JSON object and nothing else. Do not include any explanation or additional text.
        
        Best matching item (or an empty object if no confident match):
        """
        
        try:
            response = self._call_api(prompt, response_mime_type="application/json", temperature=0.1)
            extracted_text = response.json()['choices'][0]['message']['content']
            json_string = self._extract_json_from_markdown(extracted_text)
            match_data = json.loads(json_string)
            
            # The LLM is instructed to return an empty object if no match.
            # We add a confidence score here based on LLM output.
            if match_data:
                match_data['confidence_score'] = 0.8
                return match_data
            return None
        
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON response from API: {e}")
            print(f"Raw API Response: {response.text}")
            return None
        except Exception as e:
            print(f"Error calling Gemini API for match check: {e}")
            return None
