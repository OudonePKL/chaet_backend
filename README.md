# Real-Time Chat Application

A real-time chat application built with Django REST Framework and WebSocket support.

## Features

- User authentication with JWT
- Email verification with OTP
- Real-time messaging using WebSocket
- Direct and group chat support
- User online/offline status
- Message delivery status
- File sharing (profile pictures)
- Admin controls for group chats

## Prerequisites

- Python 3.8+
- Redis Server
- Virtual Environment

## Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd <repository-name>
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
- Copy `.env.example` to `.env`
- Update the variables in `.env` with your settings:
  - Set up your email credentials
  - Configure your Redis host
  - Update other settings as needed

5. Run migrations:
```bash
python manage.py makemigrations
python manage.py migrate
```

6. Create a superuser:
```bash
python manage.py createsuperuser
```

7. Start Redis server:
```bash
redis-server
```

8. Run the development server:
```bash
python manage.py runserver
```

## API Endpoints

### Authentication
- `POST /api/users/register/` - Register a new user
- `POST /api/users/verify-email/` - Verify email with OTP
- `POST /api/users/resend-otp/` - Resend OTP
- `POST /api/users/token/` - Get JWT tokens
- `POST /api/users/token/refresh/` - Refresh JWT token
- `GET/PUT /api/users/profile/` - Get/Update user profile

### Chat
- `GET/POST /api/chat/rooms/` - List/Create chat rooms
- `GET /api/chat/rooms/<id>/` - Get chat room details
- `GET/POST /api/chat/rooms/<id>/messages/` - List/Send messages
- `GET/POST /api/chat/rooms/<id>/members/` - List/Add members
- `POST /api/chat/direct-chat/<user_id>/` - Start/Get direct chat

### WebSocket
- `ws://localhost:8000/ws/chat/<room_id>/` - WebSocket connection for real-time chat

## WebSocket Events

### Connect
```javascript
const socket = new WebSocket('ws://localhost:8000/ws/chat/1/');
```

### Send Message
```javascript
socket.send(JSON.stringify({
    'message': 'Hello, World!'
}));
```

### Receive Message
```javascript
socket.onmessage = function(e) {
    const data = JSON.parse(e.data);
    console.log(data.message);
    console.log(data.sender);
    console.log(data.timestamp);
};
```

## Security Considerations

1. Email verification is required before login
2. JWT tokens expire after 1 hour
3. Refresh tokens are rotated and blacklisted after use
4. WebSocket connections require authentication
5. CORS is configured for frontend origin
6. Sensitive settings are managed through environment variables

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request 