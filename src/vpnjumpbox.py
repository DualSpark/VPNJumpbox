from environmentbase.cli import CLI
from environmentbase.networkbase import NetworkBase
from environmentbase.template import Template
from environmentbase import environmentbase as eb, resources
from troposphere import Ref, Join, Tags, FindInMap, GetAtt, Output
from troposphere.ec2 import Subnet, Route, RouteTable, SubnetRouteTableAssociation, EIP, SecurityGroup, SecurityGroupRule
from troposphere.iam import Policy
from troposphere.autoscaling import AutoScalingGroup, LaunchConfiguration, Tag as ASGTag
from troposphere.policies import CreationPolicy, ResourceSignal

FACTORY_DEFAULTS = {
    "instance_type": "t2.micro",
    "remote_access_cidr": "0.0.0.0/0",
    "ec2_key": "dualspark_rsa",
    "subnet_cidrs": ['10.0.192.0/28', '10.0.192.32/28', '10.0.192.64/28'],
    "admin_user": "openvpn"
}

CONFIG_SCHEMA = {
    "instance_type": "str",
    "remote_access_cidr": "str",
    "ec2_key": "str",
    "subnet_cidrs": "list",
    "admin_user": "str"
}

ASSOC_EIP_POLICY = Policy(
    PolicyName='cloudformationRead',
    PolicyDocument={
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "cloudformation:DescribeStackEvents",
                    "cloudformation:DescribeStackResource",
                    "cloudformation:DescribeStackResources",
                    "cloudformation:DescribeStacks",
                    "cloudformation:ListStacks",
                    "cloudformation:ListStackResources"],
                "Resource": "*"
            }, {
                "Effect": "Allow",
                "Action": [
                    "ec2:AllocateAddress",
                    "ec2:AssociateAddress",
                    "ec2:DescribeAddresses",
                    "ec2:DisassociateAddress"
                ],
                "Resource": ["*"]
            }
        ]
    })

JUMPBOX_USERDATA = resources.get_resource('jumpbox_userdata.sh', __name__)

AMI_NAME = 'openVpn2020'
SUBNET_LABEL = 'jumpbox'


class VPNJumpbox(Template):

    def __init__(self,
                 subnet_cidrs=FACTORY_DEFAULTS['subnet_cidrs'],
                 instance_type=FACTORY_DEFAULTS['instance_type'],
                 remote_access_cidr=FACTORY_DEFAULTS['remote_access_cidr'],
                 ec2_key=FACTORY_DEFAULTS['ec2_key'],
                 admin_user=FACTORY_DEFAULTS['admin_user']):

        super(VPNJumpbox, self).__init__('VPNJumpbox')

        self.subnet_cidrs = subnet_cidrs
        self.instance_type = instance_type
        self.remote_access_cidr = remote_access_cidr
        self.ec2_key = ec2_key
        self.admin_user = admin_user

    @staticmethod
    def get_factory_defaults():
        return {"jumpbox": FACTORY_DEFAULTS}

    @staticmethod
    def get_config_schema():
        return {"jumpbox": CONFIG_SCHEMA}

    # Called after add_child_template() has attached common parameters and some instance attributes:
    # - RegionMap: Region to AMI map, allows template to be deployed in different regions without updating AMI ids
    # - ec2Key: keyname to use for ssh authentication
    # - vpcCidr: IP block claimed by whole VPC
    # - vpcId: resource id of VPC
    # - commonSecurityGroup: sg identifier for common allowed ports (22 in from VPC)
    # - utilityBucket: S3 bucket name used to send logs to
    # - availabilityZone[0-3]: Indexed names of AZs VPC is deployed to
    # - [public|private]Subnet[0-9]: indexed and classified subnet identifiers
    #
    # and some instance attributes referencing the attached parameters:
    # - self.vpc_cidr
    # - self.vpc_id
    # - self.common_security_group
    # - self.utility_bucket
    # - self.subnets: keyed by type and index (e.g. self.subnets['public'][1])
    # - self.azs: List of parameter references
    def build_hook(self):

        if len(self.subnet_cidrs) != len(self.azs):
            raise ValueError('VPNJumpbox: Wrong number of CIDRs, should be %s' % len(self.azs))

        eip = self.add_resource(EIP(
            "%sEIP" % self.name,
            Domain="vpc",
        ))

        asg_name = '%sAutoscalingGroup' % self.name
        launch_config = self._get_launch_config(asg_name, eip)

        subnets = self._add_subnets()

        asg = self.add_resource(AutoScalingGroup(
            asg_name,
            AvailabilityZones=self.azs,
            LaunchConfigurationName=Ref(launch_config),
            MaxSize=1,
            MinSize=1,
            DesiredCapacity=1,
            VPCZoneIdentifier=subnets,
            CreationPolicy=CreationPolicy(
                ResourceSignal=ResourceSignal(
                    Count=1,
                    Timeout='PT10M'
                )
            ),
            DependsOn=[]))

        asg.Tags = [ASGTag('Name', self.name, True)]

        self.add_output(Output(
            'JumpboxEIP',
            Value=Ref(eip)
        ))

    def _get_launch_config(self, asg_name, eip):

        # Stole comments on port binding from here:
        # https://docs.openvpn.net/how-to-tutorialsguides/virtual-platforms/amazon-ec2-appliance-ami-quick-start-guide/

        # 22 - SSH, used to remotely administrate your appliance. It is recommended that you restrict this port to
        # trusted IP addresses. If you do not want to do this, leave the source as 0.0.0.0/0. To restrict ports to a
        # specific subnet, enter the port number, then the subnet in CIDR notation (e.g. 12.34.56.0/24). For single IP
        # addresses, /32 will need to be appended at the end (e.g. 22.33.44.55/32 for IP address 22.33.44.55). Click the
        # Add Rule button when you are done with the rule, repeat the process as needed.
        ssh_port = SecurityGroupRule(FromPort=22, ToPort=22, IpProtocol='tcp', CidrIp=self.remote_access_cidr)

        # 443 - HTTPS, used by OpenVPN Access Server for the Client Web Server. This is the interface used by your
        # users to log on to the VPN server and retrieve their keying and installation information. It is recommended
        # that you leave this open to the world (i.e. leaving the source as 0.0.0.0/0). The OpenVPN Admin Web UI by
        # default is also enabled on this port, although this can be turned off in the settings. In multi-daemon mode,
        # the OpenVPN TCP daemon shares this port alongside with the Client Web Server, and your clients will initiate
        # TCP based VPN sessions under this port number.
        openvpn_auth_port = SecurityGroupRule(FromPort=443, ToPort=443, IpProtocol='tcp', CidrIp="0.0.0.0/0")

        # 1194 - OpenVPN UDP port, used by your clients to initiate UDP based VPN sessions to the VPN server. This is
        # the preferred way for your clients to communicate and this port should be open to all of your clients. You may
        # change this port number in the settings to a non-standard port in the Admin Web UI if desired.
        openvpn_vpn_port = SecurityGroupRule(FromPort=1194, ToPort=1194, IpProtocol='udp', CidrIp="0.0.0.0/0")

        # 943 - The port number used by the Admin Web UI. By default, the Admin Web UI is also served on port 443. For
        # security reasons, you can turn this setting off and restrict the Admin Web UI port to trusted IP addresses
        # only.
        openvpn_admin_port = SecurityGroupRule(FromPort=943, ToPort=943, IpProtocol='tcp', CidrIp=self.remote_access_cidr)

        # Create LaunchConfig, ASG
        sg = self.add_resource(
            SecurityGroup(
                '%sSecurityGroup' % self.name,
                GroupDescription='Security group for %s' % self.name,
                VpcId=Ref(self.vpc_id),
                SecurityGroupIngress=[
                    openvpn_auth_port,
                    openvpn_admin_port,
                    openvpn_vpn_port,
                    ssh_port
                ])
        )

        instance_profile = self.add_instance_profile(self.name, [ASSOC_EIP_POLICY], self.name)

        startup_vars = []
        startup_vars.append(Join('=', ['EIP_ALLOC_ID', GetAtt(eip, "AllocationId")]))
        startup_vars.append(Join('=', ['REGION', Ref("AWS::Region")]))
        startup_vars.append(Join('=', ['STACKNAME', Ref("AWS::StackName")]))
        startup_vars.append(Join('=', ['ASG_NAME', asg_name]))
        startup_vars.append(Join('=', ['public_hostname', Ref(eip)]))
        startup_vars.append(Join('=', ['admin_user', self.admin_user]))
        user_data = self.build_bootstrap(
            [JUMPBOX_USERDATA],
            prepend_line='#!/bin/bash -x',
            variable_declarations=startup_vars)

        launch_config = self.add_resource(LaunchConfiguration(
            '%sLaunchConfiguration' % self.name,
            IamInstanceProfile=Ref(instance_profile),
            ImageId=FindInMap('RegionMap', Ref('AWS::Region'), AMI_NAME),
            InstanceType=self.instance_type,
            SecurityGroups=[Ref(self.common_security_group), Ref(sg)],
            KeyName=self.ec2_key,
            AssociatePublicIpAddress=True,
            InstanceMonitoring=True,
            UserData=user_data))

        return launch_config

    def _add_subnet_to_az(self, az, cidr, suffix):
        subnet = self.add_resource(Subnet(
            "%sSubnet%s" % (self.name, suffix),
            VpcId=Ref(self.vpc_id),
            AvailabilityZone=az,
            CidrBlock=cidr,
            Tags=Tags(
                Name=Join("", [Ref("AWS::StackName"), "-public"]),
            )
        ))

        route_tbl = self.add_resource(RouteTable(
            "%sRouteTable%s" % (self.name, suffix),
            VpcId=Ref(self.vpc_id),
            Tags=Tags(Name=Join("", [Ref("AWS::StackName"), "-public"]))
        ))

        route = self.add_resource(Route(
            "%sRoute%s" % (self.name, suffix),
            GatewayId=Ref(self.igw),
            DestinationCidrBlock="0.0.0.0/0",
            RouteTableId=Ref(route_tbl),
        ))

        subnet_route_tbl_assoc = self.add_resource(SubnetRouteTableAssociation(
            "%sSubnetRouteAssoc%s" % (self.name, suffix),
            SubnetId=Ref(subnet),
            RouteTableId=Ref(route_tbl),
        ))

        return subnet

    def _add_subnets(self):
        subnets = []
        az_index = 0
        for az in self.azs:
            cidr = self.subnet_cidrs[az_index]
            suffix = 'az%s' % az_index
            subnet = self._add_subnet_to_az(az, cidr, suffix)

            subnets.append(Ref(subnet))
            az_index += 1

        # Save subnets for external reference
        self.subnets[SUBNET_LABEL] = subnets

        return subnets


class TestEnv(NetworkBase):

    # Override the default create action to construct a test harness for testing VPNJumpbox pattern
    def create_action(self):
        # Create the top-level cloudformation template
        self.initialize_template()

        # Attach the NetworkBase: VPN, routing tables, public/private/protected subnets, NAT instances
        self.construct_network()

        self.add_child_template(VPNJumpbox())

        # Serialize top-level template to file
        self.write_template_to_file()


def main():
    TestEnv(
        view=CLI(),
        env_config=eb.EnvConfig(
            config_handlers=[VPNJumpbox]
        )
    )

if __name__ == '__main__':
    main()
