1. Request an SSL Certificate in AWS (ACM)
First, we will request a free SSL certificate for your domain (e.g., dev-api.kapuletu.co.ke) using AWS Certificate Manager (ACM) in the us-east-1 region. AWS will generate a validation CNAME record.

2. Validate the Domain in Truehost
You will log into your Truehost portal, go to the DNS Manager, and create the CNAME record provided by AWS. This proves to AWS that you own the domain, and they will issue the SSL certificate.

3. Configure the Serverless Framework
We will add the serverless-domain-manager plugin to your serverless.yml in the backend. The configuration will look like this:

yaml
custom:
  customDomain:
    domainName: dev-api.kapuletu.co.ke
    certificateName: dev-api.kapuletu.co.ke
    basePath: ''
    stage: ${self:provider.stage}
    createRoute53Record: false # Set to false because Truehost is your DNS provider, not AWS Route53
4. Final Truehost Routing
When we deploy the backend, we run serverless create_domain. AWS will generate a target domain name that looks like this: d-x8y9z123.execute-api.us-east-1.amazonaws.com. You will go back to Truehost one last time and add a CNAME record pointing dev-api to that AWS target domain.

That is it! All SSL termination and API routing will be handled securely by AWS, while Truehost remains your DNS provider.

This confirms that the dns module currently in your Terraform infrastructure is completely unnecessary and should be removed as planned.

Are you ready to proceed with executing the Terraform fixes in the implementation plan? If so, just let me know or click