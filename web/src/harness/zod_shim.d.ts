// A compact typing of the part of Zod the exercises use. The runtime is the real
// Zod 4 bundle; these types only drive the in-browser type checker.
declare module "zod" {
  interface ZodIssue { code: string; path: (string | number)[]; message: string }
  interface ZodError { issues: ZodIssue[]; message: string; name: string }
  type SafeParseResult<T> =
    | { success: true; data: T; error?: undefined }
    | { success: false; error: ZodError; data?: undefined };
  interface ZodType<T> {
    readonly _output: T;
    parse(data: unknown): T;
    safeParse(data: unknown): SafeParseResult<T>;
    optional(): ZodType<T | undefined>;
    nullable(): ZodType<T | null>;
    array(): ZodArray<ZodType<T>>;
    default(value: Exclude<T, undefined>): ZodType<Exclude<T, undefined>>;
    describe(description: string): this;
    refine(check: (value: T) => boolean, message?: string): this;
  }
  interface ZodString extends ZodType<string> {
    min(n: number, message?: string): ZodString;
    max(n: number, message?: string): ZodString;
  }
  interface ZodNumber extends ZodType<number> {
    min(n: number, message?: string): ZodNumber;
    max(n: number, message?: string): ZodNumber;
    int(): ZodNumber;
  }
  interface ZodArray<I extends ZodType<any>> extends ZodType<I["_output"][]> {
    min(n: number, message?: string): ZodArray<I>;
  }
  type Shape = { [key: string]: ZodType<any> };
  type OptionalKeys<S extends Shape> = { [K in keyof S]: undefined extends S[K]["_output"] ? K : never }[keyof S];
  type RequiredKeys<S extends Shape> = Exclude<keyof S, OptionalKeys<S>>;
  type Flatten<T> = { [K in keyof T]: T[K] } & {};
  type ObjectOutput<S extends Shape> = Flatten<
    { [K in RequiredKeys<S>]: S[K]["_output"] } & { [K in OptionalKeys<S>]?: S[K]["_output"] }
  >;
  interface ZodObject<S extends Shape> extends ZodType<ObjectOutput<S>> {
    readonly shape: S;
    extend<E extends Shape>(extra: E): ZodObject<Flatten<Omit<S, keyof E> & E>>;
  }
  export const z: {
    string(): ZodString;
    number(): ZodNumber;
    boolean(): ZodType<boolean>;
    unknown(): ZodType<unknown>;
    any(): ZodType<any>;
    literal<const L extends string | number | boolean>(value: L): ZodType<L>;
    enum<const T extends readonly [string, ...string[]]>(values: T): ZodType<T[number]> & { readonly options: T };
    array<I extends ZodType<any>>(item: I): ZodArray<I>;
    object<S extends Shape>(shape: S): ZodObject<S>;
    union<const T extends readonly [ZodType<any>, ...ZodType<any>[]]>(options: T): ZodType<T[number]["_output"]>;
    discriminatedUnion<const T extends readonly [ZodObject<any>, ...ZodObject<any>[]]>(key: string, options: T): ZodType<T[number]["_output"]>;
    record<V extends ZodType<any>>(key: ZodType<string>, value: V): ZodType<Record<string, V["_output"]>>;
    toJSONSchema(schema: ZodType<any>): Record<string, any>;
  };
  export namespace z {
    type infer<T extends ZodType<any>> = T["_output"];
  }
}
