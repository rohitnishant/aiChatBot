// Get references to DOM elements
const num1Input = document.getElementById('num1');
const num2Input = document.getElementById('num2');
const operationSelect = document.getElementById('operation');
const calculateButton = document.getElementById('calculate');
const resultDiv = document.getElementById('result');

// Add event listener to the calculate button
calculateButton.addEventListener('click', () => {
    // Get input values
    const num1 = parseFloat(num1Input.value);
    const num2 = parseFloat(num2Input.value);
    const operation = operationSelect.value;

    // Perform calculation
    let result;
    switch (operation) {
        case 'add':
            result = num1 + num2;
            break;
        case 'subtract':
            result = num1 - num2;
            break;
        case 'multiply':
            result = num1 * num2;
            break;
        case 'divide':
            result = num2 !== 0 ? num1 / num2 : 'Error: Division by zero!';
            break;
        default:
            result = 'Invalid operation!';
            break;
    }

    // Display the result
    resultDiv.textContent = `Result: ${result}`;
});