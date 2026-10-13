import { readFile, writeFile } from "node:fs/promises";
import openapiTS, { astToString } from "openapi-typescript";

const schema = new URL("../../openapi.json", import.meta.url);
const output = new URL("../../src/api/schema.d.ts", import.meta.url);
const contents = astToString(
  await openapiTS(schema, { defaultNonNullable: false, alphabetize: true }),
);
if (process.argv.includes("--check")) {
  if ((await readFile(output, "utf8").catch(() => "")) !== contents) {
    throw new Error(
      "API types changed: run npm run generate:api and commit src/api/schema.d.ts",
    );
  }
  console.log("Generated API types match OpenAPI.");
} else {
  await writeFile(output, contents);
  console.log("Generated src/api/schema.d.ts from openapi.json");
}
