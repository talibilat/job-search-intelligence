export function isSafeGeneratedApiPathSegment(value: string) {
  const trimmedValue = value.trim();
  const hasControlCharacter = Array.from(value).some((character) => {
    const characterCode = character.charCodeAt(0);

    return characterCode <= 0x1f || characterCode === 0x7f;
  });

  return (
    trimmedValue.length > 0 &&
    trimmedValue === value &&
    !hasControlCharacter &&
    !/[%\\/?#]/.test(value)
  );
}

export function isSafeApplicationRouteId(value: string) {
  return isSafeGeneratedApiPathSegment(value);
}

export function safeDecodeApplicationRouteSegment(value: string) {
  try {
    const decodedValue = decodeURIComponent(value);

    return isSafeApplicationRouteId(decodedValue) ? decodedValue : null;
  } catch {
    return null;
  }
}

export function applicationDetailPathForId(value: string) {
  return isSafeApplicationRouteId(value) ? `/applications/${encodeURIComponent(value)}` : null;
}
