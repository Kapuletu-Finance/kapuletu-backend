# Use the official AWS Lambda Python 3.11 base image
FROM public.ecr.aws/lambda/python:3.11

# Install system dependencies (needed for some Python libraries)
RUN yum install -y gcc-c++ make

# Copy requirements file
COPY requirements.txt .

# Install dependencies directly into the container
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler
CMD [ "main.handler" ]
