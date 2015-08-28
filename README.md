# VPNJumpbox

This EnvironmentBase pattern consists of the following components:
* Small subnet per availability zone (/28, 11 available IPs)
* One cross-AZ autoscaling group with fixed min/max size of 1 for self-healing
* Launch config containing OpenVPN community AMI
* One Elastic IP

When a jumpbox is destroyed or shutdown, the EIP is disassociated but not released back to Amazon.  The autoscaling group 
will spin up a new jumpbox. The new instance will initially have a different public IP while it configures itself.  
After a few minutes it will attach the EIP used by the previous instance.  At this point OpenVPN should be accessible.

There is no initial password. You will need to ssh in and run: `sudo passwd openvpn`

Detailed setup instructions here:
https://docs.openvpn.net/how-to-tutorialsguides/virtual-platforms/amazon-ec2-appliance-ami-quick-start-guide/

SSH access: `ssh -i <key_path> openvpnas@<eip>`
Where key_path is the key file for named key in `config.json::template.ec2_key_default` and eip is the ip address output

Admin panel: `https://<eip>/admin`
Change configuration settings, create and manager users, network access, etc

Initial user access: `https://<eip>`
Includes link to client software after authenticating

If you want to reset all the OpenVPN settings you can run the setup CLI wizard: `ovpn-init --ec`