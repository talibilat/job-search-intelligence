export interface RouteQueryParam<TValue> {
  readonly key: string;
  readonly defaultValue: TValue;
  parse(values: readonly string[]): TValue;
  serialize(value: TValue): readonly string[];
}

type RouteQuerySchema = Record<string, RouteQueryParam<unknown>>;

type RouteQueryValues<TSchema extends RouteQuerySchema> = {
  [Key in keyof TSchema]: TSchema[Key] extends RouteQueryParam<infer TValue>
    ? TValue
    : never;
};

export function parseRouteQuery<const TSchema extends RouteQuerySchema>(
  search: string | URLSearchParams,
  schema: TSchema,
): RouteQueryValues<TSchema> {
  const params = toSearchParams(search);
  const result = {} as RouteQueryValues<TSchema>;

  for (const name of objectKeys(schema)) {
    const param = schema[name];
    result[name] = param.parse(params.getAll(param.key)) as RouteQueryValues<TSchema>[typeof name];
  }

  return result;
}

export function routeQueryString<const TSchema extends RouteQuerySchema>(
  values: RouteQueryValues<TSchema>,
  schema: TSchema,
): string {
  const params = new URLSearchParams();

  for (const name of objectKeys(schema)) {
    const param = schema[name];
    const serializedValues = param.serialize(values[name]);
    for (const value of serializedValues) {
      params.append(param.key, value);
    }
  }

  const query = params.toString();
  return query ? `?${query}` : "";
}

export function updateRouteQuery<const TSchema extends RouteQuerySchema>(
  search: string | URLSearchParams,
  patch: Partial<RouteQueryValues<TSchema>>,
  schema: TSchema,
): string {
  return routeQueryString(
    {
      ...parseRouteQuery(search, schema),
      ...patch,
    },
    schema,
  );
}

export function stringQueryParam(key: string, defaultValue = ""): RouteQueryParam<string> {
  return {
    key,
    defaultValue,
    parse(values) {
      return values.at(-1) ?? defaultValue;
    },
    serialize(value) {
      return value === defaultValue ? [] : [value];
    },
  };
}

export function stringListQueryParam(key: string): RouteQueryParam<readonly string[]> {
  return {
    key,
    defaultValue: [],
    parse(values) {
      return values.filter((value) => value.length > 0);
    },
    serialize(value) {
      return value.filter((item) => item.length > 0);
    },
  };
}

export function enumQueryParam<const TValue extends string>(
  key: string,
  allowedValues: readonly TValue[],
  defaultValue?: TValue,
): RouteQueryParam<TValue | undefined> {
  const allowedValueSet = new Set<string>(allowedValues);

  return {
    key,
    defaultValue,
    parse(values) {
      const value = values.at(-1);
      if (value !== undefined && allowedValueSet.has(value)) {
        return value as TValue;
      }

      return defaultValue;
    },
    serialize(value) {
      if (value === undefined || value === defaultValue) {
        return [];
      }

      return [value];
    },
  };
}

function toSearchParams(search: string | URLSearchParams): URLSearchParams {
  if (typeof search !== "string") {
    return new URLSearchParams(search);
  }

  return new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
}

function objectKeys<TValue extends object>(value: TValue): (keyof TValue)[] {
  return Object.keys(value) as (keyof TValue)[];
}
