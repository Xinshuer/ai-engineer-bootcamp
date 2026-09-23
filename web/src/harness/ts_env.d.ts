// Globals available to TypeScript exercises (browser page and validator).
// Written to match Node's own names so the same code runs locally with tsx.
declare var console: {
  log(...data: any[]): void;
  info(...data: any[]): void;
  warn(...data: any[]): void;
  error(...data: any[]): void;
  debug(...data: any[]): void;
};
declare function setTimeout(handler: (...args: any[]) => void, timeout?: number): number;
declare function clearTimeout(id: number | undefined): void;
declare var process: { env: Record<string, string | undefined> };

interface Response {
  readonly ok: boolean;
  readonly status: number;
  readonly statusText: string;
  json(): Promise<any>;
  text(): Promise<string>;
}
interface RequestInit {
  method?: string;
  headers?: Record<string, string>;
  body?: string;
}
declare function fetch(url: string, init?: RequestInit): Promise<Response>;

// test helpers (only the tests call these)
declare function expect(label: string, fn: () => unknown, expected: unknown): void;
declare function expectTrue(label: string, fn: () => unknown): void;
declare function expectThrows(label: string, fn: () => unknown): void;
declare function expectOutput(label: string, fn: () => void, expected: string): void;
declare function expectAsync(label: string, fn: () => Promise<unknown>, expected: unknown): void;
declare function expectTrueAsync(label: string, fn: () => Promise<unknown>): void;
declare function expectRejects(label: string, fn: () => Promise<unknown>): void;
declare const MOCK: {
  calls: { url: string; body: any }[];
  reset(seed?: number): void;
  seed(n: number): void;
  failNext(status: number, times?: number): void;
};
