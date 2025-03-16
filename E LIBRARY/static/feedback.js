document.addEventListener('DOMContentLoaded', function() {
    // Star rating logic
    const stars = document.querySelectorAll('.stars .fa-star');
    const ratingInput = document.getElementById('rating');
    
    stars.forEach(star => {
        star.addEventListener('click', function() {
            const value = this.getAttribute('data-value');
            ratingInput.value = value;
            
            stars.forEach(s => {
                if (s.getAttribute('data-value') <= value) {
                    s.classList.add('active');
                } else {
                    s.classList.remove('active');
                }
            });
        });
    });
    
    // Show/hide book selection and rating based on feedback type
    const feedbackType = document.getElementById('feedback_type');
    const bookSelection = document.getElementById('book_selection');
    const ratingSection = document.getElementById('rating_section');
    
    if (feedbackType) {
        feedbackType.addEventListener('change', function() {
            if (this.value === 'book_review') {
                bookSelection.style.display = 'block';
                ratingSection.style.display = 'block';
            } else {
                bookSelection.style.display = 'none';
                ratingSection.style.display = 'none';
            }
        });
        
        // Initialize the form display based on initial value
        if (feedbackType.value === 'book_review') {
            bookSelection.style.display = 'block';
            ratingSection.style.display = 'block';
        }
    }
    
    // Fetch recent feedback via AJAX
    function loadRecentFeedback() {
        fetch('/get-recent-feedback')
            .then(response => response.json())
            .then(feedbacks => {
                const feedbackContainer = document.querySelector('.recent-feedback');
                if (feedbackContainer) {
                    feedbackContainer.innerHTML = "<h2>Recent Feedback</h2>";
                    
                    if (feedbacks.length === 0) {
                        const noFeedback = document.createElement('p');
                        noFeedback.textContent = "No feedback yet. Be the first to share your thoughts!";
                        feedbackContainer.appendChild(noFeedback);
                    } else {
                        feedbacks.forEach(fb => {
                            const feedbackItem = document.createElement('div');
                            feedbackItem.classList.add('feedback-item');
                            
                            // Create header with username and type
                            const header = document.createElement('div');
                            header.classList.add('feedback-header');
                            
                            const userInfo = document.createElement('div');
                            const username = document.createElement('strong');
                            username.textContent = fb.username;
                            userInfo.appendChild(username);
                            
                            const category = document.createElement('span');
                            category.classList.add('feedback-category');
                            category.textContent = fb.type;
                            userInfo.appendChild(category);
                            
                            header.appendChild(userInfo);
                            
                            // Add rating if available
                            if (fb.rating) {
                                const ratingDiv = document.createElement('div');
                                ratingDiv.classList.add('feedback-stars');
                                ratingDiv.innerHTML = '★'.repeat(fb.rating) + '☆'.repeat(5 - fb.rating);
                                header.appendChild(ratingDiv);
                            }
                            
                            feedbackItem.appendChild(header);
                            
                            // Add book title if available
                            if (fb.book_title) {
                                const bookDiv = document.createElement('div');
                                bookDiv.classList.add('feedback-book');
                                bookDiv.textContent = fb.book_title;
                                feedbackItem.appendChild(bookDiv);
                            }
                            
                            // Add message
                            const messageDiv = document.createElement('div');
                            messageDiv.classList.add('feedback-message');
                            messageDiv.textContent = fb.message;
                            feedbackItem.appendChild(messageDiv);
                            
                            // Add date
                            const dateDiv = document.createElement('div');
                            dateDiv.classList.add('feedback-date');
                            dateDiv.textContent = fb.created_at;
                            feedbackItem.appendChild(dateDiv);
                            
                            feedbackContainer.appendChild(feedbackItem);
                        });
                    }
                }
            })
            .catch(error => console.error('Error loading feedback:', error));
    }
    
    // Load recent feedback when page loads