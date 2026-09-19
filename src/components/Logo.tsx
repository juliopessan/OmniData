export function LogoMark() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" fill="currentColor" />
      <circle cx="16" cy="16" r="8.5" fill="none" stroke="var(--paper)" strokeWidth="2" />
      <circle cx="16" cy="16" r="2.6" fill="var(--paper)" />
      <circle cx="24.5" cy="16" r="1.8" fill="var(--paper)" />
    </svg>
  );
}
export function Logo() {
  return (
    <span className="logo">
      <LogoMark />
      OmniData
    </span>
  );
}
