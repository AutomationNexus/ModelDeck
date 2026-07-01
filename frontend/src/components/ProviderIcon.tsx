interface Props { provider: string; }

const LABELS: Record<string, string> = {
  codex: "OAI",
  claude: "CLD",
  cursor: "CUR",
};

export function ProviderIcon({ provider }: Props) {
  return (
    <div className={`provider-icon ${provider}`}>
      {LABELS[provider] ?? provider.slice(0, 3).toUpperCase()}
    </div>
  );
}
