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
    const message = messageInput.value.trim();
    if (!message && !selectedFile) return;

    // Add user message to chat
    addMessageToChat('user', message);
    messageInput.value = '';

    // Prepare form data
    const formData = new FormData();
    if (message) {
      formData.append('message', message);
    }
    if (selectedFile) {
      formData.append('file', selectedFile);
      fileNameDisplay.textContent = '';
      selectedFile = null;
    }

    try {
      const response = await fetch('http://your-backend-url/agent-workflow', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        throw new Error('Network response was not ok');
      }

      const data = await response.json();
      addMessageToChat('bot', data.response);
    } catch (error) {
      console.error('Error:', error);
      addMessageToChat('bot', 'Sorry, there was an error processing your request.');
    }
  }

  function addMessageToChat(sender, message) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', `${sender}-message`);
    messageDiv.textContent = message;
    chatContainer.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }

  // Event listeners
  sendButton.addEventListener('click', sendMessage);
  messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
});