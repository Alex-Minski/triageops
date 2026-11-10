export interface AppConfig {
  apiUrl: string;
  region: string;
  userPoolId: string;
  userPoolClientId: string;
  demo?: boolean;
}

let config: AppConfig | null = null;

/** config.json is written next to index.html by the CDK deployment, so one build works in any account. */
export async function loadConfig(): Promise<AppConfig> {
  if (config) return config;
  const demo = new URLSearchParams(window.location.search).has('demo');
  if (!demo) {
    try {
      const res = await fetch('/config.json', { cache: 'no-store' });
      if (res.ok) {
        config = (await res.json()) as AppConfig;
        return config;
      }
    } catch {
      /* fall through to demo mode */
    }
  }
  config = { apiUrl: '', region: '', userPoolId: '', userPoolClientId: '', demo: true };
  return config;
}

export function getConfig(): AppConfig {
  if (!config) throw new Error('config not loaded');
  return config;
}
