#~EIP_ALLOC_ID=
#~REGION=
#~STACKNAME=
#~ASG_NAME=
#~admin_user=
#~public_hostname=

# multiverse repo needed for python, whch is needed for aws-cfn-bootstrap tools
apt-add-repository multiverse
apt-get update

apt-get -y install ec2-api-tools

# Get instance id from metadata service
instanceid=`wget -q -O - http://169.254.169.254/latest/meta-data/instance-id`

# Required to run aws commands
source /etc/profile

# Install cfn bootstrap tools
apt-get -y install python-setuptools
mkdir aws-cfn-bootstrap-latest
cfn_bootstrap_url=https://s3.amazonaws.com/cloudformation-examples/aws-cfn-bootstrap-latest.tar.gz
curl $cfn_bootstrap_url | tar xz -C aws-cfn-bootstrap-latest --strip-components 1
easy_install aws-cfn-bootstrap-latest

# default hostname (NONE) prevents access, can use ip or hostname
export public_hostname

export admin_user

#reroute gateway traffic through the vpn (default 0=no)
reroute_gw=1

#reroute dns traffic through the vpn (default 0=no)
reroute_dns=1

#up to 2 concurrent connections w/ no license
#license=<optional. enter license here if you have one>

# grab EIP (ejecting old public ip since this one will be stable across instances)
ec2-associate-address -a $EIP_ALLOC_ID -i $instanceid --region $REGION

# signal cloudformation that we are done provisioning this instance
cfn-signal -e 0 --resource $ASG_NAME --stack $STACKNAME --region $REGION