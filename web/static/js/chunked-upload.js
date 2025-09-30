// Chunked file upload for large files
class ChunkedUploader {
    constructor(file, chunkSize = 10 * 1024 * 1024) { // 10MB chunks
        this.file = file;
        this.chunkSize = chunkSize;
        this.totalChunks = Math.ceil(file.size / chunkSize);
        this.uploadedChunks = 0;
        this.uploadId = 'upload_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    async uploadChunk(chunkIndex) {
        const start = chunkIndex * this.chunkSize;
        const end = Math.min(start + this.chunkSize, this.file.size);
        const chunk = this.file.slice(start, end);

        const formData = new FormData();
        formData.append('chunk', chunk);
        formData.append('chunkIndex', chunkIndex);
        formData.append('totalChunks', this.totalChunks);
        formData.append('uploadId', this.uploadId);
        formData.append('filename', this.file.name);

        const response = await fetch('/api/upload-chunk', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`Failed to upload chunk ${chunkIndex}`);
        }

        return await response.json();
    }

    async upload(progressCallback) {
        try {
            for (let i = 0; i < this.totalChunks; i++) {
                await this.uploadChunk(i);
                this.uploadedChunks++;
                
                if (progressCallback) {
                    progressCallback(this.uploadedChunks, this.totalChunks);
                }
            }

            // Finalize upload
            const finalizeResponse = await fetch('/api/finalize-upload', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    uploadId: this.uploadId,
                    filename: this.file.name,
                    totalSize: this.file.size
                })
            });

            return await finalizeResponse.json();

        } catch (error) {
            await this.cleanup();
            throw error;
        }
    }

    async cleanup() {
        try {
            await fetch('/api/cleanup-upload', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    uploadId: this.uploadId
                })
            });
        } catch (error) {
            console.warn('Failed to cleanup upload:', error);
        }
    }
}