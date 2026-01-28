import { Component, createSignal, Show } from 'solid-js';
import { logger } from './logger';
import { branding } from './config';

const API_URL = import.meta.env.VITE_API_URL || '';

interface FeedbackModalProps {
  isOpen: boolean;
  onClose: () => void;
  token: string;
}

type FeedbackType = 'bug' | 'feature' | 'other';

const FeedbackModal: Component<FeedbackModalProps> = (props) => {
  const [feedbackType, setFeedbackType] = createSignal<FeedbackType>('bug');
  const [message, setMessage] = createSignal('');
  const [showContact, setShowContact] = createSignal(false);
  const [contactName, setContactName] = createSignal('');
  const [contactEmail, setContactEmail] = createSignal('');
  const [contactPhone, setContactPhone] = createSignal('');
  const [contactCompany, setContactCompany] = createSignal('');
  const [isSubmitting, setIsSubmitting] = createSignal(false);
  const [error, setError] = createSignal<string | null>(null);
  const [success, setSuccess] = createSignal(false);

  const resetForm = () => {
    setFeedbackType('bug');
    setMessage('');
    setShowContact(false);
    setContactName('');
    setContactEmail('');
    setContactPhone('');
    setContactCompany('');
    setError(null);
    setSuccess(false);
  };

  const handleClose = () => {
    resetForm();
    props.onClose();
  };

  const handleSubmit = async (e: Event) => {
    e.preventDefault();
    
    if (!message().trim()) {
      setError('Please enter a message');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const baseUrl = API_URL || window.location.origin;
      
      // Build contact object if any fields are filled
      const contact = showContact() ? {
        name: contactName().trim() || null,
        email: contactEmail().trim() || null,
        phone: contactPhone().trim() || null,
        company: contactCompany().trim() || null,
      } : null;

      const response = await fetch(`${baseUrl}/feedback/submit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${props.token}`,
        },
        body: JSON.stringify({
          type: feedbackType(),
          message: message().trim(),
          logs: logger.getLogs(),
          userAgent: navigator.userAgent,
          contact,
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to submit feedback');
      }

      setSuccess(true);
      
      // Close modal after showing success
      setTimeout(() => {
        handleClose();
      }, 1500);

    } catch (err) {
      console.error('Feedback submission error:', err);
      setError(err instanceof Error ? err.message : 'Failed to submit feedback');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleOverlayClick = (e: MouseEvent) => {
    if (e.target === e.currentTarget) {
      handleClose();
    }
  };

  return (
    <Show when={props.isOpen}>
      <div class="modal-overlay" onClick={handleOverlayClick}>
        <div class="modal-content">
          <div class="modal-header">
            <h2>Send Feedback</h2>
            <button class="modal-close" onClick={handleClose}>&times;</button>
          </div>

          <Show when={success()}>
            <div class="feedback-success">
              <span class="success-icon">✓</span>
              <p>Thank you for your feedback!</p>
            </div>
          </Show>

          <Show when={!success()}>
            <form onSubmit={handleSubmit}>
              <div class="feedback-type-buttons">
                <button
                  type="button"
                  class={`type-btn ${feedbackType() === 'bug' ? 'active' : ''}`}
                  onClick={() => setFeedbackType('bug')}
                  disabled={isSubmitting()}
                >
                  🐛 Bug
                </button>
                <button
                  type="button"
                  class={`type-btn ${feedbackType() === 'feature' ? 'active' : ''}`}
                  onClick={() => setFeedbackType('feature')}
                  disabled={isSubmitting()}
                >
                  💡 Feature
                </button>
                <button
                  type="button"
                  class={`type-btn ${feedbackType() === 'other' ? 'active' : ''}`}
                  onClick={() => setFeedbackType('other')}
                  disabled={isSubmitting()}
                >
                  💬 Other
                </button>
              </div>

              <div class="form-group">
                <label for="feedback-message">Message</label>
                <textarea
                  id="feedback-message"
                  value={message()}
                  onInput={(e) => setMessage(e.target.value)}
                  placeholder="Describe the issue or suggestion..."
                  rows={4}
                  disabled={isSubmitting()}
                  required
                />
              </div>

              <div class="contact-toggle">
                <button
                  type="button"
                  class="toggle-contact-btn"
                  onClick={() => setShowContact(!showContact())}
                >
                  {showContact() ? '▼' : '▶'} Contact me (optional)
                </button>
              </div>

              <Show when={showContact()}>
                <div class="contact-fields">
                  <div class="form-group">
                    <label for="contact-name">Name</label>
                    <input
                      id="contact-name"
                      type="text"
                      value={contactName()}
                      onInput={(e) => setContactName(e.target.value)}
                      placeholder="Your name"
                      disabled={isSubmitting()}
                    />
                  </div>
                  <div class="form-group">
                    <label for="contact-email">Email</label>
                    <input
                      id="contact-email"
                      type="email"
                      value={contactEmail()}
                      onInput={(e) => setContactEmail(e.target.value)}
                      placeholder="your@email.com"
                      disabled={isSubmitting()}
                    />
                  </div>
                  <div class="form-group">
                    <label for="contact-phone">Phone</label>
                    <input
                      id="contact-phone"
                      type="tel"
                      value={contactPhone()}
                      onInput={(e) => setContactPhone(e.target.value)}
                      placeholder="(555) 123-4567"
                      disabled={isSubmitting()}
                    />
                  </div>
                  <div class="form-group">
                    <label for="contact-company">Company</label>
                    <input
                      id="contact-company"
                      type="text"
                      value={contactCompany()}
                      onInput={(e) => setContactCompany(e.target.value)}
                      placeholder="Your company"
                      disabled={isSubmitting()}
                    />
                  </div>
                </div>
              </Show>

              <Show when={error()}>
                <div class="feedback-error">{error()}</div>
              </Show>

              <div class="modal-actions">
                <button
                  type="button"
                  class="cancel-btn"
                  onClick={handleClose}
                  disabled={isSubmitting()}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  class="submit-btn"
                  disabled={isSubmitting() || !message().trim()}
                >
                  {isSubmitting() ? 'Sending...' : 'Send Feedback'}
                </button>
              </div>

              <p class="logs-note">
                📋 Browser logs will be attached to help with debugging
              </p>
            </form>
          </Show>
        </div>
      </div>
    </Show>
  );
};

export default FeedbackModal;
