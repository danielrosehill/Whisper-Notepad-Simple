# Context Data Extraction

## Description

Extracts and reformats context data in third person for use in AI system context windows

## Requires JSON Output

No

## Prompt

```
Your task is to take the text submitted by the user. Then apply the following edits: Extract only the specific context data from the following text that would be useful for setting context in an AI system. Identify the user by name and reformat the content in third person. Convert first-person references to third-person statements. Present the information as a streamlined, condensed series of factual statements without commentary. Focus only on relevant context data such as preferences, background information, technical details, and specific requirements. You must then return the text to the user edited with no text before or after.
```
