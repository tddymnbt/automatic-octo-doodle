# Secret Handling Rules

## MANDATORY RULES

1. **Never read `.env` or any file matching `.env*` except `.env.example`.**
2. **Never print, display, summarize, transform, copy, or expose secret values.**
3. **Never ask the user to paste secrets into chat.**
4. **Never commit `.env` or any credential file.**
5. **Never include real API keys or access tokens in code, tests, fixtures, logs, screenshots, documentation, or examples.**
6. **Use environment-variable names only**, for example `GEMINI_API_KEY`.
7. **Use placeholders in documentation**: `<GEMINI_API_KEY>`, `<META_PAGE_ACCESS_TOKEN>`.
8. **Do not run commands** such as `cat .env`, `type .env`, `Get-Content .env`, `printenv`, or equivalent secret-dumping commands.
9. **Do not recursively dump environment variables** for debugging.
10. **When debugging authentication**, verify only presence/absence and safe metadata, never the credential value.
11. **Before modifying secret handling**, stop and request approval.
12. **Secrets must enter the application only through environment variables or GitHub Actions secrets.**

## VERIFICATION

When asked to verify environment setup, you may:
- Check if `.env` file exists (not its contents)
- Verify environment variable names are configured
- Confirm `.gitignore` includes `.env` patterns
- Report "credentials present/absent" without revealing values

## DOCUMENTATION

When documenting configuration:
- Use variable names: `GEMINI_API_KEY`
- Use placeholders: `<YOUR_API_KEY_HERE>`
- Reference `.env.example` for structure
- Never include real values

## TESTING

- Tests must not depend on real credentials
- Use mocked values for API keys in tests
- Fixture files must contain only placeholders
- Never commit test files containing real secrets

## VIOLATIONS

Any rule violation must be immediately:
1. Reported to the user
2. Reverted if possible
3. Documented in the incident log
