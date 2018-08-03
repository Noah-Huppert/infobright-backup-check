from typing import Dict


def find_instance_by_name(ec2, name: str) -> Dict[str, object]:
    """ Finds an EC2 instance by its name
    Args:
        - ec2: AWS EC2 API client
        - name: Name of EC2 instance to find

    Raises:
        - ValueError: If EC2 instance with name could not be found

    Returns: EC2 instance object
    """
    instances_resp = ec2.describe_instances(Filters=[{
        'Name': 'tag:Name',
        'Values': [name]
    }])

    instances_rs = instances_resp['Reservations']

    if len(instances_rs) == 0:
        raise ValueError("Could not find EC2 instance with name: \"{}\"".format(name))

    if len(instances_rs) != 1:
        raise ValueError("Multiple EC2 instances found with name: \"{}\"".format(name))

    instance = instances_rs[0]['Instances'][0]

    return instance
