/** Normalize at save time only; editing must retain the exact input and caret. */
export function appearanceTags(values: string[]): string[] {
  return values
    .flatMap((value) => value.split(/[,，\n]+/))
    .map((tag) => tag.trim())
    .filter(Boolean);
}
