from environmentbase.cli import CLI
from environmentbase.networkbase import NetworkBase
from environmentbase.template import Template
from environmentbase import environmentbase as eb
from troposphere import Ref, Join, Tags
from troposphere.ec2 import Subnet, Route, RouteTable, SubnetRouteTableAssociation, EIP, SecurityGroup


class VPNJumpbox(Template):
    DEFAULT_CIDRS = ['10.0.192.0/28','10.0.192.32/28', '10.0.192.64/28']
    def __init__(self, subnet_cidrs=None):
        self.subnet_cidrs = VPNJumpbox.DEFAULT_CIDRS
        super(VPNJumpbox, self).__init__('VPNJumpbox')

    @staticmethod
    def get_factory_defaults():
        return {"jumpbox": {
            "instance_type_default": "t2.micro",
            "remote_access_cidr": "0.0.0.0/0"
        }}

    @staticmethod
    def get_config_schema():
        return {"jumpbox": {
            "instance_type_default": "str",
            "remote_access_cidr": "str"
        }}

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

        # DefaultPrivateRoute = self.add_resource(Route(
        #     "DefaultPrivateRoute",
        #     InstanceId=Ref("Nat"),
        #     DestinationCidrBlock="0.0.0.0/0",
        #     RouteTableId=Ref("PrivateRouteTable"),
        # ))
        #
        # PublicRouteTable = self.add_resource(RouteTable(
        #     "PublicRouteTable",
        #     VpcId=Ref(self.vpc_id),
        #     Tags=Tags(
        #         Name=Join("",[Ref("AWS::StackName"),"-public"]),
        #     )
        # ))
        #
        # NatEIP = self.add_resource(EIP(
        #     "NatEIP",
        #     InstanceId=Ref("Nat"),
        #     Domain="vpc",
        # ))

        if len(self.subnet_cidrs) != len(self.azs):
            raise ValueError('VPNJumpbox: Wrong number of CIDRs, should be %s' % len(self.azs))

        self.subnets['VPCJumpbox'] = []

        az_index = 0
        for az in self.azs:
            cidr = self.subnet_cidrs[az_index]
            subnet = self._add_jumpbox_to_az(az, cidr, 'az%s' % az_index)
            self.subnets['VPCJumpbox'].append(subnet)
            az_index += 1

        # Create LaunchConfig, ASG
        jumpbox_sg_name = '%sSecurityGroup' % self.name
        jumpbox_sg = self.add_resource(
            SecurityGroup(
                jumpbox_sg_name,
                GroupDescription='Security group for %s' % self.name,
                VpcId=Ref(self.vpc_id))
        )

        jumpbox_asg = self.add_asg(
            layer_name=self.name,
            security_groups=[jumpbox_sg_name, self.common_security_group]
        )

    def _add_jumpbox_to_az(self, az, cidr, suffix):
        subnet = self.add_resource(Subnet(
            "jumpboxSubnet%s" % suffix,
            VpcId=Ref(self.vpc_id),
            AvailabilityZone=az,
            CidrBlock=cidr,
            Tags=Tags(
                Name=Join("", [Ref("AWS::StackName"), "-public"]),
            )
        ))

        route_tbl = self.add_resource(RouteTable(
            "jumpboxRouteTable%s" % suffix,
            VpcId=Ref(self.vpc_id),
            Tags=Tags(Name=Join("", [Ref("AWS::StackName"), "-public"]))
        ))

        route = self.add_resource(Route(
            "jumpboxRoute%s" % suffix,
            GatewayId=Ref(self.igw),
            DestinationCidrBlock="0.0.0.0/0",
            RouteTableId=Ref(route_tbl),
        ))

        subnet_route_tbl_assoc = self.add_resource(SubnetRouteTableAssociation(
            "jumpboxSubnetRouteSssoc%s" % suffix,
            SubnetId=Ref(subnet),
            RouteTableId=Ref(route_tbl),
        ))

        return subnet



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
