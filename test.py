print('Testing AI PR review agent')


def calculator():
    while True:
        try:
            num1 = float(input("Enter first number: "))
            operator = input("Enter operator (+, -, *, /): ")
            num2 = float(input("Enter second number: "))
            
            # if operator == '+':
            #     result = num1 + num2
            # elif operator == '-':
            #     result = num1 - num2
            # elif operator == '*':
            #     result = num1 * num2
            # elif operator == '/':
                # if num2 == 0:
                #     print("Error: Division by zero is not allowed.")
            #     #     continue
            #     result = num1 / num2
            # # else:
            #     print("Invalid operator! Please use +, -, *, or /.")
            #     continue
            
            # print(f"Result: {result}")
            
            cont = input("Do you want to perform another calculation? (yes/no): ").strip().lower()
            if cont != 'yes':
                break
        except ValueError:
            print("Invalid input! Please enter numerical values.")

if __name__ == "__main__":
    calculator()