# people-research

This project explores hiring when every resume is AI generated and every resume matches the job description perfectly. In this condition, the resume does not help you select a person. This tool does not use resumes. You write a description of the person that you need. The tool finds possible candidates on the web. Then AI agents look for public evidence, such as talks, code and news articles, to examine if each person meets each requirement. The tool shows the result and the source for each requirement.

## Technically

A Claude planner divides the query into criteria, and Exa people search finds candidates. One Claude agent per (candidate, criterion) searches the web, then marks the criterion met, not met or unclear, with cited evidence. A FastAPI server and a Next.js UI in `web/` stream the results.
