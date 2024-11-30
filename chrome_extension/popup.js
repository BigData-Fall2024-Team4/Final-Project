let selectedFile = null;

document.addEventListener('DOMContentLoaded', function() {
    const chatContainer = document.getElementById('chat-container');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-btn');
    const uploadButton = document.getElementById('upload-btn');
    const fileInput = document.getElementById('file-input');
    const fileNameDisplay = document.getElementById('file-name');

    // Handle file selection
    uploadButton.addEventListener('click', () => {
        fileInput.click();
    });

    fileInput.addEventListener('change', (event) => {
        selectedFile = event.target.files[0];
        if (selectedFile) {
            fileNameDisplay.textContent = `Selected file: ${selectedFile.name}`;
        }
    });

    // Handle sending messages
    async function sendMessage() {
        try {
            const message = messageInput.value.trim();
            if (!message && !selectedFile) return;

            // Add user message to chat
            addMessageToChat('user', message);
            messageInput.value = '';

            let response;

            if (selectedFile) {
                // If there's a file, use FormData
                const formData = new FormData();
                formData.append('message', message);
                formData.append('file', selectedFile);

                response = await fetch('http://localhost:8000/agent-workflow/form', {
                    method: 'POST',
                    body: formData
                });

                // Clear file selection
                fileNameDisplay.textContent = '';
                selectedFile = null;
            } else {
                // Regular text message - use JSON format
                response = await fetch('http://localhost:8000/agent-workflow', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        query: message
                    })
                });
            }

            if (!response.ok) {
                const errorData = await response.text();
                console.error('Server Error:', errorData);
                throw new Error(`Server error: ${response.status}`);
            }

            const data = await response.json();
            
            // Handle different response formats
            const botResponse = data.response || data.error || 'No response from server';
            addMessageToChat('bot', botResponse);

        } catch (error) {
            console.error('Error:', error);
            addMessageToChat('bot', 'Sorry, there was an error processing your request. Please try again.');
        }
    }

    function addMessageToChat(sender, message) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', `${sender}-message`);
        
        // Add timestamp
        const timestamp = new Date().toLocaleTimeString();
        const timeSpan = document.createElement('span');
        timeSpan.classList.add('timestamp');
        timeSpan.textContent = timestamp;
        
        // Create message content div
        const contentDiv = document.createElement('div');
        contentDiv.classList.add('message-content');
        contentDiv.textContent = message;
        
        // Add sender label
        const senderLabel = document.createElement('div');
        senderLabel.classList.add('sender-label');
        senderLabel.textContent = sender === 'user' ? 'You' : 'Assistant';
        
        // Assemble message components
        messageDiv.appendChild(senderLabel);
        messageDiv.appendChild(contentDiv);
        messageDiv.appendChild(timeSpan);
        
        chatContainer.appendChild(messageDiv);
        
        // Auto-scroll to bottom
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    // Event listeners for sending messages
    sendButton.addEventListener('click', sendMessage);
    
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Keep input focus
    messageInput.addEventListener('blur', () => {
        // Small delay to ensure other click events are processed
        setTimeout(() => {
            if (document.activeElement !== fileInput) {
                messageInput.focus();
            }
        }, 100);
    });

    // Initial focus
    messageInput.focus();
});