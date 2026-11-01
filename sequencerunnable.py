from dotenv import load_dotenv
load_dotenv()

from langchain_google_genai import GoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Prompt Template:
prompt=ChatPromptTemplate.from_template(
    "Explain {topic} in simple words"
)

# Model:
model=GoogleGenerativeAI(model="gemini-3.6-flash")

# Output Parser
parser=StrOutputParser()


chain= prompt | model | parser  # dont consider it chain , it is runnable with chain

final_output=chain.invoke("Machine Learning")

# # step by step manual flow

# # format the prompt
# formatted_prompt=prompt.format_messages(topic="Machine Learning")

# # call the model manually
# response=model.invoke(formatted_prompt)

# #parse the output manually
# final_output=parser.parse(response)

print(final_output)