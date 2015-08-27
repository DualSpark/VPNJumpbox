#~EIP_ALLOC_ID=
#~REGION=
#~STACKNAME=
#~ASG_NAME=

# Get instance id from metadata service
instanceid=`wget -q -O - http://169.254.169.254/latest/meta-data/instance-id`

# Required to run aws commands
source /etc/profile

# grab EIP (ejecting old public ip since this one will be stable across instances)
ec2-associate-address -a $EIP_ALLOC_ID -i $instanceid --region $REGION

# signal cloudformation that we are done provisioning this instance
cfn-signal -e 0 --resource $ASG_NAME --stack $STACKNAME --region $REGION