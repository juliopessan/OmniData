/** Marca OmniData: quadrado + anel + órbita. Mesma geometria do favicon (src/app/icon.svg).
 *  O anel usa --logo-ring para contrastar com o quadrado em fundos escuros (ex.: painel do login). */
export function LogoMark() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="6" fill="currentColor" />
      <circle cx="16" cy="16" r="8.5" fill="none" stroke="var(--logo-ring, var(--paper))" strokeWidth="2" />
      <circle cx="16" cy="16" r="2.6" fill="var(--logo-ring, var(--paper))" />
      <circle cx="24.5" cy="16" r="1.8" fill="var(--logo-ring, var(--paper))" />
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
