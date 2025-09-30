// Main JavaScript functionality for Financial Transcription Suite

class TranscriptionApp {
    constructor() {
        this.currentJobId = null;
        this.pollInterval = null;
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadSettings();
        
        // Check API key status if we're on the main page
        if (window.location.pathname === '/') {
            this.checkApiKeyStatus();
        }
    }

    // Centralized error handler
    handleError(error, prefix = 'Operation failed') {
        let message = prefix + ': ';
        if (error.message.includes('Failed to fetch')) {
            message += 'Cannot connect to server. Please check if the server is running.';
        } else if (error.message.includes('ChunkedUploader')) {
            message += 'Upload system not ready. Please refresh the page and try again.';
        } else if (error.message.includes('JSON')) {
            message += 'Server returned invalid response. Check server logs.';
        } else {
            message += error.message;
        }
        this.showAlert(message, 'danger');
    }

    bindEvents() {
        // File input change
        const fileInput = document.getElementById('fileInput');
        if (fileInput) {
            fileInput.addEventListener('change', () => {
                this.updateButtonStates();
            });
        }

        // URL input change
        const urlInput = document.getElementById('urlInput');
        if (urlInput) {
            urlInput.addEventListener('input', () => {
                this.updateButtonStates();
            });
        }

        // Upload button
        const uploadBtn = document.getElementById('uploadBtn');
        if (uploadBtn) {
            uploadBtn.addEventListener('click', () => {
                this.handleFileUpload();
            });
        }

        // Process URL button
        const processUrlBtn = document.getElementById('processUrlBtn');
        if (processUrlBtn) {
            processUrlBtn.addEventListener('click', () => {
                this.handleUrlProcess();
            });
        }

        // Settings form
        const settingsForm = document.getElementById('settingsForm');
        if (settingsForm) {
            settingsForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.saveSettings();
            });
        }

        // Test email button
        const testEmailBtn = document.getElementById('testEmailBtn');
        if (testEmailBtn) {
            testEmailBtn.addEventListener('click', () => {
                this.testEmail();
            });
        }

        // Email checkbox
        const sendEmailCheckbox = document.getElementById('sendEmail');
        if (sendEmailCheckbox) {
            sendEmailCheckbox.addEventListener('change', () => {
                this.toggleEmailSettings();
            });
        }
    }

    updateButtonStates() {
        // File upload button
        const fileInput = document.getElementById('fileInput');
        const uploadBtn = document.getElementById('uploadBtn');
        if (fileInput && uploadBtn) {
            uploadBtn.disabled = !fileInput.files[0];
        }
        
        // URL process button
        const urlInput = document.getElementById('urlInput');
        const processUrlBtn = document.getElementById('processUrlBtn');
        if (urlInput && processUrlBtn) {
            processUrlBtn.disabled = !urlInput.value.trim();
        }
    }

    toggleEmailSettings() {
        const sendEmailCheckbox = document.getElementById('sendEmail');
        const emailSettings = document.getElementById('emailSettings');
        
        if (sendEmailCheckbox && emailSettings) {
            if (sendEmailCheckbox.checked) {
                emailSettings.classList.remove('d-none');
            } else {
                emailSettings.classList.add('d-none');
            }
        }
    }

    async handleFileUpload() {
        const fileInput = document.getElementById('fileInput');
        const file = fileInput.files[0];
        
        if (!file) {
            this.showAlert('Please select a file', 'warning');
            return;
        }

        // TEMPORARY: Force chunked upload for ALL files in dev environment to bypass nginx
        // This works around nginx file size limits in VS Code dev containers
        const maxDirectUploadSize = 1 * 1024 * 1024; // 1MB - force chunked upload for everything larger
        const maxTotalSize = 5 * 1024 * 1024 * 1024; // 5GB total limit
        
        if (file.size > maxTotalSize) {
            const fileSizeGB = (file.size / 1024 / 1024 / 1024).toFixed(1);
            this.showAlert('File too large (' + fileSizeGB + 'GB). Maximum size is 5GB.', 'warning');
            return;
        }

        // Use chunked upload for almost all files to bypass nginx
        if (file.size > maxDirectUploadSize) {
            return this.handleChunkedUpload(file);
        }
        
        if (!window.hasApiKey) {
            this.showAlert('Please configure your OpenAI API key in Settings first', 'warning');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        try {
            this.showProcessingStatus('Uploading file...');
            
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            // Handle specific HTTP status codes
            if (response.status === 413) {
                throw new Error('File too large. The file size exceeds the server limit. Please try a smaller file.');
            }

            // Check if the response is actually JSON
            const contentType = response.headers.get('content-type');
            
            if (!contentType || !contentType.includes('application/json')) {
                const htmlText = await response.text();
                console.error('Server returned HTML instead of JSON:', htmlText);
                
                // Provide specific error messages for common issues
                if (response.status === 413) {
                    throw new Error('File too large. Please try a smaller file.');
                } else if (response.status >= 500) {
                    throw new Error('Server error. Please try again later.');
                } else {
                    const errorMsg = 'Server error: Expected JSON but got ' + (contentType || 'unknown content type') + '. Response: ' + htmlText.substring(0, 200) + '...';
                    throw new Error(errorMsg);
                }
            }

            const data = await response.json();

            if (data.success) {
                this.currentJobId = data.job_id;
                this.showAlert('File uploaded successfully! Processing started.', 'success');
                this.startPolling();
            } else {
                this.hideProcessingStatus();
                this.showAlert('Upload failed: ' + data.error, 'danger');
            }
        } catch (error) {
            this.hideProcessingStatus();
            this.handleError(error, 'Upload failed');
        }
    }

    async handleChunkedUpload(file) {
        if (!window.hasApiKey) {
            this.showAlert('Please configure your OpenAI API key in Settings first', 'warning');
            return;
        }

        try {
            const fileSizeMB = (file.size / 1024 / 1024).toFixed(1);
            this.showProcessingStatus('Uploading large file (' + fileSizeMB + 'MB) in chunks...');
            
            if (typeof ChunkedUploader === 'undefined') {
                throw new Error('ChunkedUploader class not loaded. Please refresh the page.');
            }
            
            const uploader = new ChunkedUploader(file);
            
            const result = await uploader.upload((uploaded, total) => {
                const percent = Math.round((uploaded / total) * 100);
                this.showProcessingStatus('Uploading... ' + percent + '% (' + uploaded + '/' + total + ' chunks)');
            });

            if (result.success) {
                this.currentJobId = result.job_id;
                this.showAlert('Large file uploaded successfully! Processing started.', 'success');
                this.startPolling();
            } else {
                this.hideProcessingStatus();
                this.showAlert('Upload failed: ' + result.error, 'danger');
            }
        } catch (error) {
            this.hideProcessingStatus();
            console.error('Chunked upload error:', error);
            
            let errorMessage = 'Large file upload failed: ';
            if (error.message.includes('ChunkedUploader')) {
                errorMessage += 'Upload system not ready. Please refresh the page and try again.';
            } else if (error.message.includes('Failed to fetch')) {
                errorMessage += 'Cannot connect to server. Please check if the server is running.';
            } else {
                errorMessage += error.message;
            }
            
            this.showAlert(errorMessage, 'danger');
        }
    }

    async handleUrlProcess() {
        const urlInput = document.getElementById('urlInput');
        const url = urlInput.value.trim();
        
        if (!url) {
            this.showAlert('Please enter a URL', 'warning');
            return;
        }

        if (!window.hasApiKey) {
            this.showAlert('Please configure your OpenAI API key in Settings first', 'warning');
            return;
        }

        try {
            this.showProcessingStatus('Processing URL...');
            
            const response = await fetch('/api/process-url', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url: url })
            });

            const data = await response.json();

            if (data.success) {
                this.currentJobId = data.job_id;
                this.showAlert('URL processing started!', 'success');
                this.startPolling();
            } else {
                this.hideProcessingStatus();
                this.showAlert('URL processing failed: ' + data.error, 'danger');
            }
        } catch (error) {
            this.hideProcessingStatus();
            this.showAlert('URL processing failed: ' + error.message, 'danger');
        }
    }

    startPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
        }

        this.pollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/api/job-status/${this.currentJobId}`);
                const data = await response.json();

                if (data.status === 'processing') {
                    this.updateStatus(data.progress);
                } else if (data.status === 'completed') {
                    this.stopPolling();
                    this.hideProcessingStatus();
                    this.showResults(data.result);
                } else if (data.status === 'error') {
                    this.stopPolling();
                    this.hideProcessingStatus();
                    this.showAlert('Processing failed: ' + data.error, 'danger');
                }
            } catch (error) {
                this.stopPolling();
                this.hideProcessingStatus();
                this.showAlert('Status check failed: ' + error.message, 'danger');
            }
        }, 2000);
    }

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    showProcessingStatus(message) {
        const statusDiv = document.getElementById('processing-status');
        const statusMessage = document.getElementById('status-message');
        const uploadBtn = document.getElementById('uploadBtn');
        const processUrlBtn = document.getElementById('processUrlBtn');
        
        if (statusDiv) {
            statusDiv.classList.remove('d-none');
        }
        
        if (statusMessage) {
            statusMessage.textContent = message;
        }
        
        if (uploadBtn) uploadBtn.disabled = true;
        if (processUrlBtn) processUrlBtn.disabled = true;
    }

    updateStatus(message) {
        const statusMessage = document.getElementById('status-message');
        if (statusMessage) {
            statusMessage.textContent = message;
        }
    }

    hideProcessingStatus() {
        const statusDiv = document.getElementById('processing-status');
        const uploadBtn = document.getElementById('uploadBtn');
        const processUrlBtn = document.getElementById('processUrlBtn');
        
        if (statusDiv) {
            statusDiv.classList.add('d-none');
        }
        
        // Re-enable buttons based on input state
        this.toggleUploadButton();
        this.toggleUrlButton();
    }

    showResults(result) {
        // Show analysis
        const analysisContent = document.getElementById('analysis-content');
        if (analysisContent) {
            analysisContent.innerHTML = this.formatMarkdown(result.analysis);
        }
        
        // Show transcript
        const transcriptContent = document.getElementById('transcript-content');
        if (transcriptContent) {
            transcriptContent.innerHTML = '<pre class="transcript-text">' + this.escapeHtml(result.transcript) + '</pre>';
        }
        
        // Show results section
        const resultsSection = document.getElementById('results-section');
        if (resultsSection) {
            resultsSection.classList.remove('d-none');
            resultsSection.scrollIntoView({ behavior: 'smooth' });
        }

        // Show email status if available
        if (result.email_result) {
            if (result.email_result.success) {
                this.showAlert('Analysis completed and email sent successfully!', 'success');
            } else {
                this.showAlert('Analysis completed. Email failed: ' + result.email_result.message, 'warning');
            }
        } else {
            this.showAlert('Analysis completed successfully!', 'success');
        }
    }

    formatMarkdown(text) {
        // Simple markdown to HTML conversion
        return text
            .replace(/### (.*)/g, '<h5 class="text-primary mt-4 mb-3">$1</h5>')
            .replace(/## (.*)/g, '<h4 class="text-primary mt-4 mb-3">$1</h4>')
            .replace(/# (.*)/g, '<h3 class="text-primary mt-4 mb-3">$1</h3>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/- (.*)/g, '<li>$1</li>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/^(.*)$/gm, '<p>$1</p>')
            .replace(/<p><li>/g, '<ul><li>')
            .replace(/<\/li><\/p>/g, '</li></ul>');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    showAlert(message, type = 'info') {
        // Create a unique ID for this alert
        const alertId = 'alert-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        
        const alertHtml = `
            <div id="${alertId}" class="alert alert-${type} alert-dismissible fade show" role="alert">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        `;
        
        // Try to find an existing alert container, or create one
        let alertContainer = document.querySelector('.alert-container');
        if (!alertContainer) {
            alertContainer = document.createElement('div');
            alertContainer.className = 'alert-container';
            const container = document.querySelector('.container');
            if (container) {
                container.insertBefore(alertContainer, container.firstChild);
            }
        }
        
        // Append the new alert instead of replacing existing ones
        alertContainer.insertAdjacentHTML('beforeend', alertHtml);
        
        // Get the newly created alert element
        const newAlert = document.getElementById(alertId);
        
        // Set different auto-dismiss times based on message type
        let dismissTime;
        if (type === 'success') {
            dismissTime = 4000; // 4 seconds for success
        } else if (type === 'info') {
            dismissTime = 5000; // 5 seconds for info
        } else if (type === 'warning') {
            dismissTime = 8000; // 8 seconds for warnings
        } else if (type === 'danger') {
            dismissTime = 10000; // 10 seconds for errors
        }
        
        // Auto-dismiss after the specified time
        if (dismissTime) {
            setTimeout(() => {
                if (newAlert && newAlert.parentNode) {
                    newAlert.classList.remove('show');
                    newAlert.classList.add('fade');
                    // Remove the element after fade animation completes
                    setTimeout(() => {
                        if (newAlert && newAlert.parentNode) {
                            newAlert.remove();
                        }
                    }, 150); // Bootstrap fade transition is 150ms
                }
            }, dismissTime);
        }
        
        // Limit the number of alerts to prevent overflow (keep only last 5)
        const allAlerts = alertContainer.querySelectorAll('.alert');
        if (allAlerts.length > 5) {
            for (let i = 0; i < allAlerts.length - 5; i++) {
                allAlerts[i].remove();
            }
        }
    }

    async loadSettings() {
        try {
            const response = await fetch('/api/get-settings');
            const settings = await response.json();
            
            // Populate settings form if it exists
            if (document.getElementById('settingsForm')) {
                this.populateSettingsForm(settings);
            }
        } catch (error) {
            console.error('Error loading settings:', error);
        }
    }

    populateSettingsForm(settings) {
        const fields = [
            'openaiApiKey',
            'sendEmail',
            'emailAddress',
            'emailPassword',
            'outputEmail',
            'vimeoClientId',
            'vimeoClientSecret',
            'vimeoAccessToken'
        ];

        fields.forEach(fieldId => {
            const element = document.getElementById(fieldId);
            if (element) {
                const settingKey = fieldId.replace(/([A-Z])/g, '_$1').toLowerCase();
                
                if (element.type === 'checkbox') {
                    element.checked = settings[settingKey] || false;
                } else {
                    element.value = settings[settingKey] || '';
                }
            }
        });

        // Show email settings if enabled
        this.toggleEmailSettings();
    }

    async saveSettings() {
        const settings = {
            openai_api_key: document.getElementById('openaiApiKey').value,
            send_email: document.getElementById('sendEmail').checked,
            email_address: document.getElementById('emailAddress').value,
            email_password: document.getElementById('emailPassword').value,
            output_email: document.getElementById('outputEmail').value,
            vimeo_client_id: document.getElementById('vimeoClientId').value,
            vimeo_client_secret: document.getElementById('vimeoClientSecret').value,
            vimeo_access_token: document.getElementById('vimeoAccessToken').value
        };

        try {
            const response = await fetch('/api/save-settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(settings)
            });

            const data = await response.json();

            if (data.success) {
                this.showSettingsStatus('Settings saved successfully!', 'success');
                
                // Update global API key status
                window.hasApiKey = !!(settings.openai_api_key && settings.openai_api_key.trim());
                
                // If we're on the main page, refresh the API status
                if (window.location.pathname === '/') {
                    setTimeout(() => {
                        this.checkApiKeyStatus();
                    }, 500);
                }
            } else {
                this.showSettingsStatus('Error saving settings: ' + data.error, 'danger');
            }
        } catch (error) {
            this.showSettingsStatus('Error saving settings: ' + error.message, 'danger');
        }
    }

    checkApiKeyStatus() {
        fetch('/api/get-settings')
            .then(response => response.json())
            .then(settings => {
                const hasApiKey = settings.openai_api_key && settings.openai_api_key.trim() !== '';
                window.hasApiKey = hasApiKey;
                
                const warningAlert = document.getElementById('api-status-alert');
                const successAlert = document.getElementById('api-status-success');
                
                if (warningAlert && successAlert) {
                    if (hasApiKey) {
                        warningAlert.classList.add('d-none');
                        successAlert.classList.remove('d-none');
                    } else {
                        warningAlert.classList.remove('d-none');
                        successAlert.classList.add('d-none');
                    }
                }
                
                this.updateButtonStates();
            })
            .catch(error => {
                console.error('Error checking API key status:', error);
                window.hasApiKey = false;
                this.updateButtonStates();
            });
    }

    updateButtonStates() {
        const uploadBtn = document.getElementById('uploadBtn');
        const processUrlBtn = document.getElementById('processUrlBtn');
        const fileInput = document.getElementById('fileInput');
        const urlInput = document.getElementById('urlInput');
        
        if (!uploadBtn || !processUrlBtn) return;
        
        const hasApiKey = window.hasApiKey || false;
        const hasFile = fileInput && fileInput.files && fileInput.files[0];
        const hasUrl = urlInput && urlInput.value.trim();
        
        uploadBtn.disabled = !hasApiKey || !hasFile;
        processUrlBtn.disabled = !hasApiKey || !hasUrl;
        
        if (!hasApiKey) {
            uploadBtn.title = 'Please configure OpenAI API key first';
            processUrlBtn.title = 'Please configure OpenAI API key first';
        } else {
            uploadBtn.title = '';
            processUrlBtn.title = '';
        }
    }

    async testEmail() {
        const testEmailBtn = document.getElementById('testEmailBtn');
        
        if (!testEmailBtn) return;
        
        const originalHtml = testEmailBtn.innerHTML;
        testEmailBtn.disabled = true;
        testEmailBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Testing...';

        try {
            // First save current settings
            await this.saveSettings();
            
            // Then test email
            const response = await fetch('/api/test-email', {
                method: 'POST'
            });

            const data = await response.json();

            if (data.success) {
                this.showSettingsStatus('Email test successful!', 'success');
            } else {
                this.showSettingsStatus('Email test failed: ' + data.message, 'danger');
            }
        } catch (error) {
            this.showSettingsStatus('Email test failed: ' + error.message, 'danger');
        } finally {
            testEmailBtn.disabled = false;
            testEmailBtn.innerHTML = originalHtml;
        }
    }

    showSettingsStatus(message, type) {
        const statusDiv = document.getElementById('settingsStatus');
        if (statusDiv) {
            statusDiv.innerHTML = `
                <div class="alert alert-${type} alert-dismissible fade show" role="alert">
                    ${message}
                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                </div>
            `;
        }
    }
}

// Initialize the app when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.transcriptionApp = new TranscriptionApp();
});