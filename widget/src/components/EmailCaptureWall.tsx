import { useState } from 'react';

interface EmailCaptureWallProps {
  onSubmit: (email: string) => void;
  onSkip: () => void;
}

export function EmailCaptureWall({ onSubmit, onSkip }: EmailCaptureWallProps) {
  const [email, setEmail] = useState('');
  const [touched, setTouched] = useState(false);

  const valid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  const showError = touched && !valid;

  return (
    <div className="gktuition-tutor__wall" data-testid="gktuition-wall">
      <h4>Enjoying the tutor?</h4>
      <p>
        Drop your email for free unlimited access while we&apos;re in early access — no spam, just
        the occasional study tip.
      </p>
      <input
        type="email"
        placeholder="you@example.com"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        onBlur={() => setTouched(true)}
        aria-label="Email address"
        data-testid="gktuition-wall-input"
      />
      {showError ? <div className="gktuition-tutor__error">Please enter a valid email.</div> : null}
      <button
        type="button"
        disabled={!valid}
        onClick={() => onSubmit(email)}
        data-testid="gktuition-wall-submit"
      >
        Continue
      </button>
      <button
        type="button"
        onClick={onSkip}
        data-testid="gktuition-wall-skip"
        style={{
          background: 'transparent',
          color: '#6b7280',
          border: 'none',
          padding: '4px',
          fontSize: '13px',
          textDecoration: 'underline',
        }}
      >
        Maybe later
      </button>
    </div>
  );
}
