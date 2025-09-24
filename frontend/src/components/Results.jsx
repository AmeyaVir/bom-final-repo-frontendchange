import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Download, CheckCircle, X, Database, AlertCircle, Save, Plus, RefreshCw } from 'lucide-react';
import { useTranslation } from '../contexts/TranslationContext';
import Card from './ui/Card';
import Button from './ui/Button';
import toast from 'react-hot-toast';

function ResultsPage() {
  const { workflowId } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [results, setResults] = useState(null);
  const [editedResults, setEditedResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pendingItems, setPendingItems] = useState([]);
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [showApprovalSection, setShowApprovalSection] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const loadResults = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`/api/autonomous/workflow/${workflowId}/results`);
      if (!response.ok) throw new Error('Failed to fetch results');
      
      const data = await response.json();
      setResults(data);
      // Deep copy for editing
      setEditedResults(JSON.parse(JSON.stringify(data)));
    } catch (error) {
      console.error('Error fetching results:', error);
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }, [workflowId]);

  const loadPendingApprovals = useCallback(async () => {
    try {
      const response = await fetch('/api/knowledge-base/pending');
      if (response.ok) {
        const data = await response.json();
        const workflowPendingItems = data.pending_items?.filter(
          item => item.workflow_id === workflowId
        ) || [];
        setPendingItems(workflowPendingItems);
        setShowApprovalSection(workflowPendingItems.length > 0);
      }
    } catch (error) {
      console.error('Error fetching pending approvals:', error);
    }
  }, [workflowId]);

  useEffect(() => {
    if (workflowId) {
      loadResults();
      loadPendingApprovals();
    }
  }, [workflowId, loadResults, loadPendingApprovals]);

  const handleItemSelection = (itemId) => {
    const newSelected = new Set(selectedItems);
    if (newSelected.has(itemId)) {
      newSelected.delete(itemId);
    } else {
      newSelected.add(itemId);
    }
    setSelectedItems(newSelected);
  };
  
  const handleEditChange = (index, field, value) => {
    const updatedMatches = [...editedResults.matches];
    updatedMatches[index][field] = value;
    setEditedResults({ ...editedResults, matches: updatedMatches });
  };
  
  const handleDirectApprove = (index) => {
    const updatedMatches = [...editedResults.matches];
    updatedMatches[index]['action_path'] = '🟢 Auto-Register';
    toast.success(`Item '${updatedMatches[index].material_name}' marked for auto-approval.`);
    setEditedResults({ ...editedResults, matches: updatedMatches });
  };
  
  const handleAddNewItem = () => {
    const newItem = {
        qc_process_or_wi_step: "Manual Entry",
        item_type: "Consumable",
        material_name: "",
        part_number: "",
        qty: 1,
        uom: "Number",
        vendor_name: "",
        action_path: '🟢 Auto-Register',
        reasoning: "Manually added and pre-approved by user.",
        isNew: true // Flag for styling
    };
    setEditedResults({
      ...editedResults,
      matches: [newItem, ...editedResults.matches]
    });
  };

  const handleSaveChanges = async () => {
     for (const item of editedResults.matches) {
        if (!item.part_number || !item.material_name) {
            toast.error("Part Number and Material Name are mandatory for all items.");
            return;
        }
    }

    setIsSaving(true);
    try {
        const response = await fetch(`/api/autonomous/workflow/${workflowId}/results`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(editedResults)
        });
        if (!response.ok) throw new Error("Failed to save changes.");
        toast.success("Changes saved successfully!");
        // Refresh data from server
        loadResults();
    } catch (err) {
        toast.error(err.message);
    } finally {
        setIsSaving(false);
    }
  };


  const handleApproveSelected = async () => {
    if (selectedItems.size === 0) {
      toast.error('Please select items to approve');
      return;
    }

    try {
      const response = await fetch(`/api/knowledge-base/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workflow_id: workflowId,
          item_ids: Array.from(selectedItems).map(id => parseInt(id, 10))
        })
      });

      if (response.ok) {
        const data = await response.json();
        toast.success(`${data.approved_count} items approved for knowledge base`);
        loadPendingApprovals();
        setSelectedItems(new Set());
      } else {
        throw new Error('Failed to approve items');
      }
    } catch (error) {
      console.error('Error approving items:', error);
      toast.error('Failed to approve items');
    }
  };

  const handleRejectSelected = async () => {
    if (selectedItems.size === 0) {
      toast.error('Please select items to reject');
      return;
    }

    try {
      const response = await fetch(`/api/knowledge-base/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workflow_id: workflowId,
          item_ids: Array.from(selectedItems).map(id => parseInt(id, 10))
        })
      });

      if (response.ok) {
        const data = await response.json();
        toast.success(`${data.rejected_count} items rejected`);
        loadPendingApprovals();
        setSelectedItems(new Set());
      } else {
        throw new Error('Failed to reject items');
      }
    } catch (error) {
      console.error('Error rejecting items:', error);
      toast.error('Failed to reject items');
    }
  };

  const exportResults = async () => {
    try {
      const exportData = {
        workflow_id: workflowId,
        results: editedResults,
        export_date: new Date().toISOString(),
      };

      const blob = new Blob([JSON.stringify(exportData, null, 2)], {
        type: 'application/json'
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `bom-results-${workflowId}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      toast.success(t('results.resultsExported'));
    } catch (error) {
      console.error('Export failed:', error);
      toast.error('Export failed');
    }
  };
  
  if (loading) return <div className="p-6 text-center"><AlertCircle className="mx-auto h-8 w-8 animate-spin"/>Loading...</div>;
  if (error || !editedResults) return <div className="p-6 text-red-500">Error: {error}</div>;

  const matches = editedResults.matches || [];
  const summary = editedResults.summary || {};

  const editableFields = ['qc_process_or_wi_step', 'material_name', 'part_number', 'qty', 'uom', 'item_type', 'reasoning'];

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto p-6">
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <div>
              <button
                onClick={() => navigate('/dashboard')}
                className="inline-flex items-center text-sm text-gray-500 hover:text-gray-700 mb-4"
              >
                <ArrowLeft className="h-4 w-4 mr-1" />
                Back to Dashboard
              </button>
              <h1 className="text-3xl font-bold text-gray-900">{t('results.title')}</h1>
              <p className="text-gray-600 mt-1">
                {t('results.workflowId')}: {results.summary.workflow_name || workflowId}
              </p>
            </div>
            <div className="flex items-center space-x-3">
              <Button onClick={handleAddNewItem} variant="outline">
                <Plus className="h-4 w-4 mr-2" /> Add New Item
              </Button>
               <Button onClick={handleSaveChanges} disabled={isSaving}>
                <Save className="h-4 w-4 mr-2" /> {isSaving ? 'Saving...' : 'Save Changes'}
              </Button>
              <Button onClick={exportResults} variant="outline">
                <Download className="h-4 w-4 mr-2" />
                {t('results.exportResults')}
              </Button>
            </div>
          </div>
        </div>
        
        {showApprovalSection && (
          <Card className="p-6 mb-8 border-amber-200 bg-amber-50">
             <div className="flex items-start space-x-3">
              <Database className="h-6 w-6 text-amber-600 mt-0.5" />
              <div className="flex-1">
                <h3 className="text-lg font-medium text-gray-900 mb-2">
                  {t('knowledgeBase.pendingApprovals')}
                </h3>
                <p className="text-sm text-gray-600 mb-4">
                  {pendingItems.length} items from this workflow are pending approval to be added to the knowledge base.
                </p>
                <div className="space-y-3 mb-4 max-h-48 overflow-y-auto">
                  {pendingItems.map((item) => {
                    const data = item.parsed_data || {};
                    return (
                      <div
                        key={item.id}
                        className={`p-3 rounded-lg border cursor-pointer transition-colors ${selectedItems.has(item.id) ? 'bg-primary-50 border-primary-300' : 'bg-white border-gray-200 hover:border-gray-300'}`}
                        onClick={() => handleItemSelection(item.id)}
                      >
                        <div className="flex items-center space-x-2">
                              <input type="checkbox" checked={selectedItems.has(item.id)} readOnly className="rounded"/>
                              <h4 className="font-medium text-gray-900">{data.material_name}</h4>
                        </div>
                      </div>
                    );
                  })}
                </div>
                 <div className="flex items-center space-x-3">
                  <Button onClick={handleApproveSelected} disabled={selectedItems.size === 0} className="bg-green-600 hover:bg-green-700 text-white"><CheckCircle className="h-4 w-4 mr-2" />Approve ({selectedItems.size})</Button>
                  <Button onClick={handleRejectSelected} disabled={selectedItems.size === 0} variant="outline" className="text-red-700"><X className="h-4 w-4 mr-2" />Reject ({selectedItems.size})</Button>
                 </div>
              </div>
            </div>
          </Card>
        )}

        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  {['S.No.', 'Action', ...Object.keys(matches[0] || {}).filter(k => !['isNew'].includes(k))].map(h => <th key={h} className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase">{h.replace(/_/g, ' ')}</th>)}
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {matches.map((match, index) => (
                    <tr key={index} className={match.isNew ? 'bg-green-50' : 'hover:bg-gray-50'}>
                        <td className="px-3 py-2 whitespace-nowrap text-sm">{index + 1}</td>
                        <td className="px-3 py-2">
                            <Button size="sm" variant="outline" onClick={() => handleDirectApprove(index)}>
                                <CheckCircle className="h-4 w-4 text-green-500"/>
                            </Button>
                        </td>
                        {Object.keys(match).filter(k => !['isNew'].includes(k)).map(key => (
                            <td key={key} className="px-3 py-2 whitespace-nowrap text-sm">
                                {editableFields.includes(key) ? (
                                    <input 
                                        type="text"
                                        value={match[key] || ''}
                                        onChange={(e) => handleEditChange(index, key, e.target.value)}
                                        className={`w-full p-1 border rounded bg-gray-50 ${!match[key] && (key === 'part_number' || key === 'material_name') ? 'border-red-500' : 'border-gray-200'}`}
                                    />
                                ) : (
                                    <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${
                                        key === 'action_path' && match[key].includes('Auto-Register') ? 'bg-green-100 text-green-800' :
                                        key === 'action_path' && match[key].includes('Human') ? 'bg-red-100 text-red-800' :
                                        key === 'action_path' ? 'bg-yellow-100 text-yellow-800' : ''
                                    }`}>
                                        {String(match[key])}
                                    </span>
                                )}
                            </td>
                        ))}
                    </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}

export default ResultsPage;
