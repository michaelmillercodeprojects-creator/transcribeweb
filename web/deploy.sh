#!/bin/bash

# Financial Transcription Suite - Deployment Script
set -e

echo "🚀 Financial Transcription Suite - Web Deployment"
echo "=================================================="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your configuration before proceeding."
    echo "   At minimum, you need to set OPENAI_API_KEY"
    exit 1
fi

# Check for required environment variables
source .env
if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "your-openai-api-key-here" ]; then
    echo "❌ OPENAI_API_KEY is not set in .env file"
    exit 1
fi

echo "✅ Configuration validated"

# Build and start the application
echo "🔨 Building Docker image..."
docker-compose build

echo "🚀 Starting application..."
docker-compose up -d

# Wait for application to be ready
echo "⏳ Waiting for application to start..."
sleep 10

# Check if application is running
if curl -f http://localhost:5000/ > /dev/null 2>&1; then
    echo "✅ Application is running successfully!"
    echo "🌐 Access the application at: http://localhost:5000"
    echo ""
    echo "💡 Quick start:"
    echo "   1. Go to http://localhost:5000/settings to configure your API keys"
    echo "   2. Upload an audio/video file or provide a URL"
    echo "   3. Get your financial analysis report!"
    echo ""
    echo "📋 Management commands:"
    echo "   View logs:     docker-compose logs -f"
    echo "   Stop app:      docker-compose down"
    echo "   Restart app:   docker-compose restart"
else
    echo "❌ Application failed to start. Check logs with:"
    echo "   docker-compose logs"
fi