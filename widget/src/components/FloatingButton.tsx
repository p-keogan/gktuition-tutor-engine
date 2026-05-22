import type { WidgetOptions } from '../api/types';

interface FloatingButtonProps {
  position: NonNullable<WidgetOptions['position']>;
  isOpen: boolean;
  onClick: () => void;
}

export function FloatingButton({ position, isOpen, onClick }: FloatingButtonProps) {
  return (
    <button
      type="button"
      aria-label={isOpen ? 'Close AI tutor' : 'Open AI tutor'}
      aria-expanded={isOpen}
      className={`gktuition-tutor__fab gktuition-tutor__fab--${position}`}
      onClick={onClick}
      data-testid="gktuition-fab"
    >
      {isOpen ? '×' : '?'}
    </button>
  );
}
