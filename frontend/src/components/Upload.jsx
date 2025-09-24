import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Upload, File, Database, ToggleLeft, ToggleRight, Cloud } from 'lucide-react';
import { useTranslation } from '../contexts/TranslationContext';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import toast from 'react-hot-toast';

// Helper component for cloud provider buttons
const CloudConnectButton = ({ provider, icon, onClick }) => (
    <button onClick={onClick} className="flex items-center justify-center w-full p-4 border rounded-lg hover:bg-gray-50 transition-colors">
        <img src={icon} alt={`${provider} logo`} className="h-8 w-8 mr-4"/>
        <span className="text-lg font-medium text-gray-700">Connect to {provider}</span>
    </button>
);

function UploadPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [wiDocument, setWiDocument] = useState(null);
  const [itemMaster, setItemMaster] = useState(null);
  const [comparisonMode, setComparisonMode] = useState('full');
  const [uploading, setUploading] = useState(false);
  const [activeTab, setActiveTab] = useState('single'); // 'single' or 'batch'
  const [workflowName, setWorkflowName] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);

  const handleFileChange = (event, type) => {
    const file = event.target.files[0];
    if (type === 'wi') {
      setWiDocument(file);
    } else {
      setItemMaster(file);
    }
  };

  const toggleComparisonMode = () => {
    setComparisonMode(comparisonMode === 'full' ? 'kb_only' : 'full');
    if (comparisonMode === 'full') {
      setItemMaster(null);
    }
  };

  const promptForWorkflowName = () => {
    if (!wiDocument) {
      toast.error('Please select a WI document');
      return;
    }
    if (comparisonMode === 'full' && !itemMaster) {
      toast.error('Please select an Item Master for full comparison mode');
      return;
    }
    setIsModalOpen(true);
  };
  
  const handleUpload = async () => {
    if (!workflowName.trim()) {
        toast.error('Please enter a name for the workflow.');
        return;
    }

    setIsModalOpen(false);
    try {
      setUploading(true);
      const formData = new FormData();
      formData.append('wi_document', wiDocument);
      formData.append('workflow_name', workflowName);
      formData.append('comparison_mode', comparisonMode);
      
      if (itemMaster) {
        formData.append('item_master', itemMaster);
      }
      const response = await fetch('/api/autonomous/upload', {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Upload failed');
      }
      const data = await response.json();
      if (data.success) {
        toast.success('Upload successful!');
        navigate(`/processing/${data.workflow_id}`);
      } else {
        throw new Error(data.message || 'Upload failed');
      }
    } catch (error) {
      console.error('Upload error:', error);
      toast.error('Upload failed: ' + error.message);
    } finally {
      setUploading(false);
      setWorkflowName('');
    }
  };
  
  const handleCloudConnect = (provider) => {
    toast.loading(`Redirecting to ${provider} for authentication...`);
    // This would redirect to your backend's auth endpoint
    // window.location.href = `/api/auth/${provider.toLowerCase()}/start`;
    
    // For demonstration, we'll just show a success message.
    setTimeout(() => {
        toast.dismiss();
        toast.success(`Authenticated with ${provider}. You can now select a folder.`);
        // Here you would typically open a file/folder picker UI
    }, 2000);
  };
  
  const renderWorkflowNameModal = () => {
    if (!isModalOpen) return null;
    
    return (
      <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full flex items-center justify-center z-50">
        <div className="bg-white p-8 rounded-lg shadow-xl w-full max-w-md">
          <h2 className="text-xl font-bold mb-4">Name Your Workflow</h2>
          <p className="text-gray-600 mb-6">Please provide a name for this workflow for easy identification.</p>
          <input
            type="text"
            value={workflowName}
            onChange={(e) => setWorkflowName(e.target.value)}
            placeholder={"e.g., WI-Doc-Analysis-Q4"}
            className="w-full px-3 py-2 border border-gray-300 rounded-md mb-6"
          />
          <div className="flex justify-end space-x-4">
            <Button variant="outline" onClick={() => {setIsModalOpen(false); setWorkflowName('');}}>Cancel</Button>
            <Button onClick={handleUpload} disabled={uploading}>
              {uploading ? 'Processing...' : 'Start Processing'}
            </Button>
          </div>
        </div>
      </div>
    );
  };


  return (
    <div className="min-h-screen bg-gray-50">
       {renderWorkflowNameModal()}
      <div className="max-w-4xl mx-auto p-6">
        <div className="mb-8">
          <button onClick={() => navigate('/dashboard')} className="inline-flex items-center text-sm text-gray-500 hover:text-gray-700 mb-4">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Back to Dashboard
          </button>
          <h1 className="text-3xl font-bold text-gray-900">{t('navigation.upload')}</h1>
          <p className="text-gray-600 mt-1">
            Upload a single document or start a batch process from a cloud location.
          </p>
        </div>
        
        <div className="mb-6 border-b border-gray-200">
            <nav className="-mb-px flex space-x-8">
                <button onClick={() => setActiveTab('single')} className={`py-4 px-1 border-b-2 font-medium text-sm ${activeTab === 'single' ? 'border-primary-500 text-primary-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}`}>
                    <File className="h-5 w-5 mr-2 inline"/>Single Document Upload
                </button>
                <button onClick={() => setActiveTab('batch')} className={`py-4 px-1 border-b-2 font-medium text-sm ${activeTab === 'batch' ? 'border-primary-500 text-primary-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}`}>
                    <Cloud className="h-5 w-5 mr-2 inline"/>Batch Processing from Cloud
                </button>
            </nav>
        </div>

        {activeTab === 'single' && (
          <>
            <Card className="p-6 mb-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-medium text-gray-900">Comparison Mode</h3>
                  <p className="text-sm text-gray-500 mt-1">
                    Choose how to compare your WI document
                  </p>
                </div>
                <div className="flex items-center space-x-4">
                  <span className={`text-sm font-medium ${
                    comparisonMode === 'full' ? 'text-primary-600' : 'text-gray-500'
                  }`}>
                    Full Comparison
                  </span>
                  <button onClick={toggleComparisonMode} className="focus:outline-none">
                    {comparisonMode === 'full' ? (
                      <ToggleRight className="h-8 w-8 text-primary-600" />
                    ) : (
                      <ToggleLeft className="h-8 w-8 text-gray-400" />
                    )}
                  </button>
                  <span className={`text-sm font-medium ${
                    comparisonMode === 'kb_only' ? 'text-primary-600' : 'text-gray-500'
                  }`}>
                    Knowledge Base Only
                  </span>
                </div>
              </div>
               <div className="mt-4 p-4 bg-gray-50 rounded-lg">
                {comparisonMode === 'full' ? (
                  <div className="flex items-start space-x-3">
                    <File className="h-5 w-5 text-blue-500 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-gray-900">Full Comparison Mode</p>
                      <p className="text-sm text-gray-600">
                        Compare WI document against both Item Master and Knowledge Base for comprehensive matching
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start space-x-3">
                    <Database className="h-5 w-5 text-purple-500 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-gray-900">Knowledge Base Only Mode</p>
                      <p className="text-sm text-gray-600">
                        Compare WI document against historical knowledge base only - no Item Master required
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </Card>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
              <Card className="p-6">
                <div className="text-center">
                  <File className="mx-auto h-12 w-12 text-gray-400 mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 mb-2">
                    WI/QC Document *
                  </h3>
                  <p className="text-sm text-gray-500 mb-4">
                    Supports PDF, DOCX, TXT formats
                  </p>
                  <input
                    type="file"
                    accept=".pdf,.docx,.txt"
                    onChange={(e) => handleFileChange(e, 'wi')}
                    className="hidden"
                    id="wi-upload"
                  />
                  <label
                    htmlFor="wi-upload"
                    className="cursor-pointer inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
                  >
                    <Upload className="h-4 w-4 mr-2" />
                    Choose File
                  </label>
                  {wiDocument && (
                    <div className="mt-4">
                      <p className="text-sm text-green-600 font-medium">Selected:</p>
                      <p className="text-sm text-gray-700">{wiDocument.name}</p>
                    </div>
                  )}
                </div>
              </Card>
              <Card className={`p-6 ${comparisonMode === 'kb_only' ? 'opacity-50' : ''}`}>
                <div className="text-center">
                  <File className="mx-auto h-12 w-12 text-gray-400 mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 mb-2">
                    Item Master {comparisonMode === 'full' ? '*' : ''}
                  </h3>
                  <p className="text-sm text-gray-500 mb-4">
                    {comparisonMode === 'kb_only'
                      ? 'Not required'
                      : 'Supports Excel and CSV formats'
                    }
                  </p>
                  <input
                    type="file"
                    accept=".xlsx,.xls,.csv"
                    onChange={(e) => handleFileChange(e, 'item')}
                    className="hidden"
                    id="item-upload"
                    disabled={comparisonMode === 'kb_only'}
                  />
                  <label
                    htmlFor="item-upload"
                    className={`cursor-pointer inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 ${
                      comparisonMode === 'kb_only' ? 'cursor-not-allowed' : ''
                    }`}
                  >
                    <Upload className="h-4 w-4 mr-2" />
                    Choose File
                  </label>
                  {itemMaster && comparisonMode === 'full' && (
                    <div className="mt-4">
                      <p className="text-sm text-green-600 font-medium">Selected:</p>
                      <p className="text-sm text-gray-700">{itemMaster.name}</p>
                    </div>
                  )}
                </div>
              </Card>
            </div>
             <div className="text-center">
                <Button
                    onClick={promptForWorkflowName}
                    disabled={!wiDocument || (comparisonMode === 'full' && !itemMaster) || uploading}
                    size="lg"
                  >
                    <Upload className="h-5 w-5 mr-2" />
                    Start Processing
                </Button>
            </div>
          </>
        )}

        {activeTab === 'batch' && (
          <Card className="p-6 mb-8">
              <div className="text-center">
                  <Cloud className="mx-auto h-12 w-12 text-gray-400 mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 mb-2">Process Documents from Cloud</h3>
                  <p className="text-sm text-gray-500 mb-6 max-w-lg mx-auto">
                      Connect to your cloud storage provider to select a folder. Each document in the folder will be processed as a separate workflow.
                  </p>
                  <div className="max-w-md mx-auto space-y-4">
                    <CloudConnectButton 
                        provider="SharePoint" 
                        icon="https://img.icons8.com/color/48/000000/sharepoint.png" 
                        onClick={() => handleCloudConnect('SharePoint')}
                    />
                    <CloudConnectButton 
                        provider="Google Drive" 
                        icon="https://img.icons8.com/color/48/000000/google-drive.png" 
                        onClick={() => handleCloudConnect('Google Drive')}
                    />
                  </div>
              </div>
          </Card>
        )}
      </div>
    </div>
  );
}

export default UploadPage;

